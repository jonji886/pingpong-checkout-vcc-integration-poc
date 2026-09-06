from __future__ import annotations

import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..domain.payment import PaymentStatus, transition
from ..integrations.pingpong.base import CheckoutProvider, ProviderError, ProviderPaymentResult
from ..integrations.pingpong.retry import RetryPolicy
from ..models import ApiIdempotency, PaymentOrder
from .common import find_idempotency, hash_key, new_id, payload_hash, utcnow, write_audit, write_provider_log
from .credit_service import CreditService


class ConflictError(ValueError):
    pass


class NotFoundError(ValueError):
    pass


class ForbiddenError(ValueError):
    pass


class PaymentService:
    def __init__(self, provider: CheckoutProvider, *, retry_policy: Optional[RetryPolicy] = None):
        self.provider = provider
        self.retry_policy = retry_policy or RetryPolicy()

    @staticmethod
    def validate_amount(amount: Any) -> Decimal:
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise ValueError("amount must be a decimal")
        if value <= 0 or value.as_tuple().exponent < -2:
            raise ValueError("amount must be positive with at most 2 decimal places")
        return value.quantize(Decimal("0.01"))

    def create_topup(self, db: Session, *, actor_id: str, actor_role: str, amount: Any, currency: str, idem_key: str, trace_id: str) -> tuple[PaymentOrder, Optional[dict]]:
        if not idem_key:
            raise ValueError("Idempotency-Key is required")
        if currency.upper() != "USD":
            raise ValueError("P0 only supports USD")
        value = self.validate_amount(amount)
        route = "/api/topups"
        req_hash = payload_hash({"amount": str(value), "currency": currency.upper()})
        existing = find_idempotency(db, actor_id=actor_id, method="POST", route=route, key=idem_key)
        if existing:
            if existing.request_hash != req_hash:
                raise ConflictError("idempotency key payload conflict")
            payment = db.get(PaymentOrder, existing.resource_id)
            if not payment:
                raise NotFoundError("idempotent payment missing")
            # A crash can leave the local idempotency row IN_PROGRESS. Replaying
            # the same provider identifiers is safe under Checkout idempotency
            # and can recover a one-time next_action without persisting it.
            if existing.status == "IN_PROGRESS" and payment.status in {"CREATED", "PROCESSING"}:
                try:
                    result = self.retry_policy.run(lambda: self.provider.create_payment(partner_transaction_id=payment.partner_transaction_id, provider_request_id=payment.provider_request_id, amount=Decimal(payment.amount), currency=payment.currency, user_id=payment.user_id, notify_url=settings.pingpong_notify_url or None), operation_name="create_payment_replay", request_id=payment.provider_request_id)
                    next_action = {"type": result.next_action.type}
                    if result.next_action.url: next_action["url"] = result.next_action.url
                    if result.next_action.qr_payload: next_action["qr_payload"] = result.next_action.qr_payload
                    self.apply_observation(db, payment_id=payment.id, result=result, trace_id=trace_id, source="create_replay")
                    existing.status = "COMPLETED"; existing.completed_at = utcnow()
                    db.commit()
                    return db.get(PaymentOrder, payment.id), next_action
                except ProviderError as exc:
                    payment.status = "PROCESSING" if exc.retryable else "FAILED"
                    payment.failure_code = exc.error_type
                    payment.next_reconcile_at = utcnow() + timedelta(seconds=settings.reconcile_after_seconds) if exc.retryable else None
                    db.commit()
            return payment, None
        payment_id = new_id("payment")
        partner_id = "txn_" + payment_id
        provider_request_id = "req_" + payment_id
        idem = ApiIdempotency(id=new_id("idem"), actor_id=actor_id, method="POST", canonical_route=route, key_hash=hash_key(idem_key), request_hash=req_hash, resource_type="PaymentOrder", resource_id=payment_id, status="IN_PROGRESS")
        payment = PaymentOrder(id=payment_id, user_id=actor_id, partner_transaction_id=partner_id, provider_request_id=provider_request_id, amount=value, currency="USD", status="CREATED", provider="pingpong")
        db.add(idem)
        db.add(payment)
        CreditService.ensure_account(db, actor_id)
        write_audit(db, actor_id=actor_id, actor_role=actor_role, action="CREATE_TOPUP", resource_type="PaymentOrder", resource_id=payment_id, trace_id=trace_id, outcome="ACCEPTED")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = find_idempotency(db, actor_id=actor_id, method="POST", route=route, key=idem_key)
            if existing and existing.request_hash != req_hash:
                raise ConflictError("idempotency key payload conflict")
            return db.get(PaymentOrder, existing.resource_id), None

        started = time.monotonic()
        try:
            result = self.retry_policy.run(lambda: self.provider.create_payment(partner_transaction_id=partner_id, provider_request_id=provider_request_id, amount=value, currency="USD", user_id=actor_id, notify_url=settings.pingpong_notify_url or None), operation_name="create_payment", request_id=provider_request_id)
            write_provider_log(db, provider="pingpong", operation="create_payment", trace_id=trace_id, provider_request_id=result.provider_request_id, http_status=result.http_status, provider_code=result.provider_code, latency_ms=int((time.monotonic() - started) * 1000), success=True)
            next_action = {"type": result.next_action.type}
            if result.next_action.url: next_action["url"] = result.next_action.url
            if result.next_action.qr_payload: next_action["qr_payload"] = result.next_action.qr_payload
            self.apply_observation(db, payment_id=payment_id, result=result, trace_id=trace_id, source="create")
            idem = db.get(ApiIdempotency, idem.id)
            if idem:
                idem.status = "COMPLETED"; idem.completed_at = utcnow()
            db.commit()
            return db.get(PaymentOrder, payment_id), next_action
        except ProviderError as exc:
            write_provider_log(db, provider="pingpong", operation="create_payment", trace_id=trace_id, provider_request_id=provider_request_id, http_status=exc.status_code, provider_code=None, latency_ms=int((time.monotonic() - started) * 1000), success=False, error_type=exc.error_type)
            payment = db.get(PaymentOrder, payment_id)
            payment.status = "PROCESSING" if exc.retryable else "FAILED"
            payment.failure_code = exc.error_type
            payment.failure_message = str(exc)[:255]
            if exc.retryable:
                payment.next_reconcile_at = utcnow() + timedelta(seconds=settings.reconcile_after_seconds)
            idem = db.get(ApiIdempotency, idem.id)
            if idem: idem.status = "COMPLETED"; idem.completed_at = utcnow()
            db.commit()
            return payment, None

    def apply_observation(self, db: Session, *, payment_id: str, result: ProviderPaymentResult, trace_id: str, source: str) -> str:
        payment = db.get(PaymentOrder, payment_id)
        if not payment: raise NotFoundError("payment not found")
        old = payment.status
        target = transition(old, result.provider_status)
        # A terminal local state is monotonic. Keep the last terminal provider
        # status when an older webhook arrives, so reconciliation views cannot
        # be made stale by a late PROCESSING/PENDING observation.
        if old not in {PaymentStatus.SUCCEEDED.value, PaymentStatus.FAILED.value, PaymentStatus.CANCELLED.value, PaymentStatus.REVIEW_REQUIRED.value}:
            payment.provider_status = result.provider_status
        payment.provider_transaction_id = result.provider_transaction_id or payment.provider_transaction_id
        if result.failure_code: payment.failure_code = result.failure_code
        if result.failure_message: payment.failure_message = result.failure_message[:255]
        payment.status = target
        if target == PaymentStatus.PROCESSING.value:
            payment.next_reconcile_at = utcnow() + timedelta(seconds=settings.reconcile_after_seconds)
        elif target in {PaymentStatus.SUCCEEDED.value, PaymentStatus.FAILED.value, PaymentStatus.CANCELLED.value, PaymentStatus.REVIEW_REQUIRED.value}:
            payment.next_reconcile_at = None
        if target == PaymentStatus.SUCCEEDED.value:
            CreditService.add_topup(db, user_id=payment.user_id, amount=Decimal(payment.amount), payment_id=payment.id)
        write_audit(db, actor_id=None, actor_role="system", action="PAYMENT_OBSERVATION", resource_type="PaymentOrder", resource_id=payment.id, trace_id=trace_id, outcome=target)
        return target

    def reconcile(self, db: Session, *, payment_id: str, actor_id: str, actor_role: str, trace_id: str) -> PaymentOrder:
        payment = db.get(PaymentOrder, payment_id)
        if not payment: raise NotFoundError("payment not found")
        if actor_role not in {"admin", "fde", "system"} and not (actor_role == "developer" and actor_id == payment.user_id):
            raise ForbiddenError("FDE/Admin role required")
        started = time.monotonic()
        try:
            result = self.retry_policy.run(lambda: self.provider.query_payment(partner_transaction_id=payment.partner_transaction_id, provider_request_id=payment.provider_request_id), retry_on_timeout=True, operation_name="query_payment", request_id=payment.provider_request_id)
            write_provider_log(db, provider="pingpong", operation="query_payment", trace_id=trace_id, provider_request_id=result.provider_request_id, http_status=result.http_status, provider_code=result.provider_code, latency_ms=int((time.monotonic() - started) * 1000), success=True)
            self.apply_observation(db, payment_id=payment_id, result=result, trace_id=trace_id, source="reconcile")
            payment = db.get(PaymentOrder, payment_id)
            payment.reconcile_attempts += 1
            payment.updated_at = utcnow()
            write_audit(db, actor_id=actor_id, actor_role=actor_role, action="RECONCILE_PAYMENT", resource_type="PaymentOrder", resource_id=payment_id, trace_id=trace_id, outcome="SUCCESS")
            db.commit()
        except ProviderError as exc:
            payment.reconcile_attempts += 1
            payment.next_reconcile_at = utcnow() + timedelta(seconds=settings.reconcile_after_seconds)
            write_provider_log(db, provider="pingpong", operation="query_payment", trace_id=trace_id, provider_request_id=payment.provider_request_id, http_status=exc.status_code, provider_code=None, latency_ms=int((time.monotonic() - started) * 1000), success=False, error_type=exc.error_type)
            db.commit()
        return db.get(PaymentOrder, payment_id)
