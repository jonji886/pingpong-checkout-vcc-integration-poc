from __future__ import annotations

import time
from decimal import Decimal
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.payment import RefundStatus, transition_refund
from ..integrations.pingpong.base import CheckoutProvider, ProviderError, ProviderRefundResult
from ..integrations.pingpong.retry import RetryPolicy
from ..models import ApiIdempotency, PaymentOrder, RefundOrder, CreditHold
from .common import find_idempotency, hash_key, new_id, payload_hash, utcnow, write_audit, write_provider_log
from .credit_service import CreditService
from .payment_service import ConflictError, NotFoundError


class RefundService:
    def __init__(self, provider: CheckoutProvider, *, retry_policy: RetryPolicy | None = None):
        self.provider = provider
        self.retry_policy = retry_policy or RetryPolicy()

    def create_refund(self, db: Session, *, actor_id: str, actor_role: str, payment_id: str, idem_key: str, trace_id: str) -> RefundOrder:
        if not idem_key: raise ValueError("Idempotency-Key is required")
        if actor_role not in {"finance", "admin", "fde"}:
            raise PermissionError("finance role required")
        req_hash = payload_hash({"payment_id": payment_id})
        route = "/api/refunds"
        existing = find_idempotency(db, actor_id=actor_id, method="POST", route=route, key=idem_key)
        if existing:
            if existing.request_hash != req_hash: raise ConflictError("idempotency key payload conflict")
            return db.get(RefundOrder, existing.resource_id)
        payment = db.get(PaymentOrder, payment_id)
        if not payment: raise NotFoundError("payment not found")
        if payment.status != "SUCCEEDED": raise ValueError("payment is not refundable")
        if db.query(RefundOrder).filter_by(payment_id=payment_id).first(): raise ConflictError("payment already has a refund")
        refund_id = new_id("refund")
        partner_refund_id = "rfn_" + refund_id
        provider_request_id = "req_" + refund_id
        refund = RefundOrder(id=refund_id, payment_id=payment_id, partner_refund_id=partner_refund_id, provider_request_id=provider_request_id, amount=payment.amount, currency=payment.currency, status="CREATED", provider="pingpong")
        idem = ApiIdempotency(id=new_id("idem"), actor_id=actor_id, method="POST", canonical_route=route, key_hash=hash_key(idem_key), request_hash=req_hash, resource_type="RefundOrder", resource_id=refund_id, status="IN_PROGRESS")
        db.add(refund); db.add(idem)
        # CreditHold is created before any provider call. Insufficient balance is a safe manual path.
        hold = CreditService.create_hold(db, user_id=payment.user_id, refund_id=refund_id, amount=Decimal(payment.amount))
        if hold is None:
            refund.status = transition_refund(refund.status, "MANUAL_REVIEW")
            idem.status = "COMPLETED"; idem.completed_at = utcnow()
            write_audit(db, actor_id=actor_id, actor_role=actor_role, action="CREATE_REFUND", resource_type="RefundOrder", resource_id=refund_id, trace_id=trace_id, outcome="MANUAL_REVIEW")
            db.commit()
            return refund
        refund.credit_hold_id = hold.id
        refund.status = transition_refund(refund.status, "PROCESSING")
        write_audit(db, actor_id=actor_id, actor_role=actor_role, action="CREATE_REFUND", resource_type="RefundOrder", resource_id=refund_id, trace_id=trace_id, outcome="ACCEPTED")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = find_idempotency(db, actor_id=actor_id, method="POST", route=route, key=idem_key)
            if existing and existing.request_hash != req_hash: raise ConflictError("idempotency key payload conflict")
            return db.get(RefundOrder, existing.resource_id)
        started = time.monotonic()
        try:
            result = self.retry_policy.run(lambda: self.provider.create_refund(partner_refund_id=partner_refund_id, provider_request_id=provider_request_id, partner_transaction_id=payment.partner_transaction_id, amount=Decimal(payment.amount), currency=payment.currency), operation_name="create_refund", request_id=provider_request_id)
            write_provider_log(db, provider="pingpong", operation="create_refund", trace_id=trace_id, provider_request_id=result.provider_request_id, http_status=result.http_status, provider_code=result.provider_code, latency_ms=int((time.monotonic()-started)*1000), success=True)
            self.apply_observation(db, refund_id=refund_id, result=result, trace_id=trace_id)
            idem = db.get(ApiIdempotency, idem.id)
            if idem: idem.status="COMPLETED"; idem.completed_at=utcnow()
            db.commit()
        except ProviderError as exc:
            write_provider_log(db, provider="pingpong", operation="create_refund", trace_id=trace_id, provider_request_id=provider_request_id, http_status=exc.status_code, provider_code=None, latency_ms=int((time.monotonic()-started)*1000), success=False, error_type=exc.error_type)
            refund = db.get(RefundOrder, refund_id)
            if exc.retryable:
                refund.status = transition_refund(refund.status, "PROCESSING")
            else:
                refund.status = transition_refund(refund.status, "FAILED")
                hold = db.query(CreditHold).filter_by(id=refund.credit_hold_id).one()
                CreditService.release_hold(db, hold)
            idem = db.get(ApiIdempotency, idem.id)
            if idem: idem.status="COMPLETED"; idem.completed_at=utcnow()
            db.commit()
        return db.get(RefundOrder, refund_id)

    def apply_observation(self, db: Session, *, refund_id: str, result: ProviderRefundResult, trace_id: str) -> str:
        refund = db.get(RefundOrder, refund_id)
        if not refund: raise NotFoundError("refund not found")
        refund.provider_status = result.provider_status
        refund.provider_refund_id = result.provider_refund_id or refund.provider_refund_id
        status = str(result.provider_status).upper()
        if status == "SUCCESS":
            refund.status = transition_refund(refund.status, "SUCCEEDED")
            hold = db.query(CreditHold).filter_by(id=refund.credit_hold_id).one()
            CreditService.settle_hold(db, hold, refund_id=refund.id, amount=Decimal(refund.amount))
        elif status in {"FAIL", "FAILED", "CLOSE", "CLOSED", "CANCEL"}:
            refund.status = transition_refund(refund.status, "FAILED")
            hold = db.query(CreditHold).filter_by(id=refund.credit_hold_id).one()
            CreditService.release_hold(db, hold)
        else:
            refund.status = transition_refund(refund.status, "PROCESSING")
        write_audit(db, actor_id=None, actor_role="system", action="REFUND_OBSERVATION", resource_type="RefundOrder", resource_id=refund.id, trace_id=trace_id, outcome=refund.status)
        return refund.status

    def query_refund(self, db: Session, *, refund_id: str, actor_id: str, actor_role: str, trace_id: str) -> RefundOrder:
        refund = db.get(RefundOrder, refund_id)
        if not refund: raise NotFoundError("refund not found")
        payment = db.get(PaymentOrder, refund.payment_id)
        if not payment:
            raise NotFoundError("payment not found")
        result = self.retry_policy.run(lambda: self.provider.query_refund(partner_refund_id=refund.partner_refund_id, partner_transaction_id=payment.partner_transaction_id, provider_request_id=refund.provider_request_id), retry_on_timeout=True, operation_name="query_refund", request_id=refund.provider_request_id)
        self.apply_observation(db, refund_id=refund_id, result=result, trace_id=trace_id)
        db.commit()
        return db.get(RefundOrder, refund_id)
