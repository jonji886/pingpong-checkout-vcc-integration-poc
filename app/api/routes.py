from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..agents.finance_agent import RuleBasedIntentParser, VCCIntentParser, is_unsafe_request, unsafe_request
from ..agents.tools import approval_tool, budget_tool
from ..api.schemas import TopupRequest, TopupResponse, VCCAgentRequest, VCCApproveRequest
from ..agents.schemas import PaymentRequest
from ..db import get_db
from ..integrations.pingpong.base import NextAction, ProviderPaymentResult, ProviderRefundResult
from ..integrations.pingpong.checkout_contracts import PingPongWebhookPayload
from ..integrations.pingpong.mappers import map_webhook
from ..models import AuditLog, CreditAccount, PaymentOrder, RefundOrder, User, VCCApplication, WebhookEvent, ProviderCallLog
from ..security import Principal, current_principal, require_role
from ..services.approval_service import ApprovalService
from ..services.common import new_id, payload_hash, utcnow, write_audit
from ..services.issuing_service import IssuingService
from ..services.payment_service import ConflictError, ForbiddenError, NotFoundError, PaymentService
from ..services.refund_service import RefundService
from ..services.reconciliation_service import ReconciliationService


def _explicit_provider_event_id(payload: dict[str, Any]) -> str | None:
    """Return an ID only when the provider payload explicitly supplies one."""
    for key in ("event_id", "eventId", "webhook_id", "webhookId"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _map_mock_webhook(payload: dict[str, Any]) -> PingPongWebhookPayload:
    """Map the intentionally small local Mock contract to the same DTO shape."""
    declared_type = str(payload.get("event_type") or payload.get("eventType") or payload.get("type") or "").lower()
    is_refund = "refund" in declared_type or any(key in payload for key in ("refund_id", "partner_refund_id", "refundId", "provider_refund_id"))
    from ..integrations.pingpong.checkout_contracts import _decimal_or_none, _first_str, _upper_or_none
    return PingPongWebhookPayload(
        event_type="refund" if is_refund else "payment",
        merchant_transaction_id=_first_str(payload, "partner_transaction_id", "partnerTransactionId", "merchantTransactionId"),
        transaction_id=_first_str(payload, "provider_transaction_id", "transaction_id", "transactionId", "paymentId"),
        merchant_refund_id=_first_str(payload, "partner_refund_id", "partnerRefundId", "merchantRefundId"),
        refund_id=_first_str(payload, "refund_id", "refundId", "provider_refund_id"),
        request_id=_first_str(payload, "request_id", "requestId"),
        amount=_decimal_or_none(payload.get("amount")),
        currency=_upper_or_none(payload.get("currency")),
        status=_first_str(payload, "status", "paymentStatus", "tradeStatus") or "",
        notify_type=_upper_or_none(payload.get("notifyType")),
        raw=payload,
    )


def _clarification_question(parsed: PaymentRequest) -> str | None:
    if not parsed.missing_fields:
        return None
    labels = {
        "vendor": "供应商",
        "amount": "金额",
        "currency": "币种",
        "request": "完整的用卡申请",
    }
    fields = "、".join(labels.get(item, item) for item in parsed.missing_fields)
    return "请补充：" + fields + "。"


def make_router(
    payment_service: PaymentService,
    refund_service: RefundService,
    issuing_service: IssuingService,
    intent_parser: VCCIntentParser | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    reconciliation_service = ReconciliationService(payment_service)
    intent_parser = intent_parser or RuleBasedIntentParser()

    @router.get("/me/credits")
    def credits(principal: Principal = Depends(require_role("developer", "finance", "admin", "fde")), db: Session = Depends(get_db)):
        account = db.query(CreditAccount).filter_by(user_id=principal.actor_id).first()
        if not account: return {"credit_unit": "USD_CREDIT", "posted_balance": "0.00", "available_balance": "0.00"}
        return {"credit_unit": account.credit_unit, "posted_balance": str(account.posted_balance), "available_balance": str(account.available_balance)}

    @router.post("/topups", response_model=TopupResponse)
    def topup(body: TopupRequest, request: Request, idempotency_key: str = Header(default="", alias="Idempotency-Key"), principal: Principal = Depends(require_role("developer")), db: Session = Depends(get_db)):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        try:
            payment, action = payment_service.create_topup(db, actor_id=principal.actor_id, actor_role=principal.role, amount=body.amount, currency=body.currency, idem_key=idempotency_key, trace_id=trace_id)
        except ConflictError as exc: raise HTTPException(409, str(exc))
        except ValueError as exc: raise HTTPException(400, str(exc))
        return TopupResponse(payment_id=payment.id, payment_status=payment.status, next_action=action)

    @router.get("/payments/{payment_id}")
    def get_payment(payment_id: str, request: Request, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
        payment = db.get(PaymentOrder, payment_id)
        if not payment: raise HTTPException(404, "payment not found")
        if principal.role == "developer" and payment.user_id != principal.actor_id: raise HTTPException(404, "payment not found")
        return {"payment_id": payment.id, "payment_status": payment.status, "provider_status": payment.provider_status, "provider_transaction_id": payment.provider_transaction_id, "provider_request_id": payment.provider_request_id, "partner_transaction_id": payment.partner_transaction_id, "amount": str(payment.amount), "currency": payment.currency, "created_at": payment.created_at, "updated_at": payment.updated_at, "next_reconcile_at": payment.next_reconcile_at, "refunded": bool(db.query(RefundOrder).filter_by(payment_id=payment.id, status="SUCCEEDED").first())}

    @router.post("/payments/{payment_id}/query")
    def query_payment(payment_id: str, request: Request, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
        payment = db.get(PaymentOrder, payment_id)
        if not payment: raise HTTPException(404, "payment not found")
        if principal.role == "developer" and payment.user_id != principal.actor_id: raise HTTPException(404, "payment not found")
        try: payment = payment_service.reconcile(db, payment_id=payment_id, actor_id=principal.actor_id, actor_role=principal.role, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex)
        except NotFoundError as exc: raise HTTPException(404, str(exc))
        return {"payment_id": payment.id, "payment_status": payment.status, "provider_status": payment.provider_status, "provider_transaction_id": payment.provider_transaction_id}

    @router.get("/payments")
    def list_payments(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
        query = db.query(PaymentOrder)
        if principal.role == "developer": query = query.filter(PaymentOrder.user_id == principal.actor_id)
        rows = query.order_by(PaymentOrder.created_at.desc()).limit(100).all()
        return [{"payment_id": x.id, "payment_status": x.status, "provider_status": x.provider_status, "provider_transaction_id": x.provider_transaction_id, "amount": str(x.amount), "currency": x.currency, "created_at": x.created_at} for x in rows]

    @router.post("/webhooks/pingpong/checkout")
    async def webhook(request: Request, db: Session = Depends(get_db)):
        raw = await request.body()
        signature = request.headers.get("X-Mock-Signature", "")
        from ..config import settings
        from ..integrations.pingpong.auth import PingPongAuthProvider
        verifier = PingPongAuthProvider("", "")
        if settings.pingpong_mode == "mock":
            valid = verifier.webhook_valid(raw, signature, settings.pingpong_webhook_secret)
        else:
            try:
                sandbox_payload = json.loads(raw.decode("utf-8"))
            except Exception:
                sandbox_payload = {}
            # Checkout V4 signs accId/clientId/signType/version/bizContent in-body.
            valid = isinstance(sandbox_payload, dict) and verifier.verify_v4_body(sandbox_payload, settings.pingpong_salt)
        if not valid: raise HTTPException(401, "invalid webhook signature")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            raise HTTPException(400, "invalid webhook body")
        if not isinstance(payload, dict):
            raise HTTPException(400, "invalid webhook body")

        try:
            normalized = map_webhook(payload) if settings.pingpong_mode == "sandbox" else _map_mock_webhook(payload)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "invalid webhook contract") from exc

        status_value = normalized.status.upper()
        is_refund = normalized.is_refund
        tx = normalized.merchant_transaction_id
        provider_tx = normalized.transaction_id
        amount_value = normalized.amount
        currency = normalized.currency
        request_id = normalized.request_id
        refund_resource = normalized.merchant_refund_id or normalized.refund_id
        resource = refund_resource if is_refund else (provider_tx or tx)
        event_type = "checkout.refund" if is_refund else "checkout.payment"
        provider_event_id = _explicit_provider_event_id(payload)
        delivery_fingerprint = payload_hash(payload)
        event = WebhookEvent(id=new_id("wh"), provider="pingpong", event_type=event_type, provider_event_id=provider_event_id, delivery_fingerprint=delivery_fingerprint, resource_id=str(resource) if resource else None, provider_status=status_value or None, amount=amount_value, currency=currency, payload_hash=delivery_fingerprint, delivery_id=request.headers.get("X-Delivery-Id"), status="RECEIVED")
        try:
            db.add(event); db.flush()
        except IntegrityError:
            db.rollback()
            return {"code": 200, "message": "SUCCESS"}
        if amount_value is None:
            event.status = "REJECTED"; event.error = "invalid_amount"; event.processed_at = utcnow(); db.commit()
            return {"code": 200, "message": "SUCCESS"}
        if is_refund:
            refund = db.query(RefundOrder).filter((RefundOrder.partner_refund_id == refund_resource) | (RefundOrder.provider_refund_id == refund_resource)).first()
            if not refund:
                event.status = "REJECTED"; event.error = "unknown refund"; event.processed_at = utcnow(); write_audit(db, actor_id=None, actor_role="system", action="WEBHOOK_REJECTED", resource_type="WebhookEvent", resource_id=event.id, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex, outcome="UNKNOWN_REFUND"); db.commit()
                return {"code": 200, "message": "SUCCESS"}
            if Decimal(amount_value) != Decimal(refund.amount) or (currency and currency != refund.currency):
                event.status = "REJECTED"; event.error = "amount_or_currency_mismatch"; event.processed_at = utcnow(); write_audit(db, actor_id=None, actor_role="system", action="WEBHOOK_REJECTED", resource_type="WebhookEvent", resource_id=event.id, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex, outcome="AMOUNT_OR_CURRENCY_MISMATCH"); db.commit()
                return {"code": 200, "message": "SUCCESS"}
            if status_value not in {"PENDING", "PROCESSING", "SUCCESS", "FAIL", "FAILED", "CLOSE", "CLOSED", "CANCEL"}:
                event.status = "REJECTED"; event.error = "unknown_provider_status"; event.processed_at = utcnow(); write_audit(db, actor_id=None, actor_role="system", action="WEBHOOK_REJECTED", resource_type="WebhookEvent", resource_id=event.id, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex, outcome="UNKNOWN_PROVIDER_STATUS"); db.commit()
                return {"code": 200, "message": "SUCCESS"}
            old_refund = refund.status
            refund_service.apply_observation(db, refund_id=refund.id, result=ProviderRefundResult(provider_refund_id=refund_resource, provider_request_id=str(request_id or refund.provider_request_id), provider_status=status_value), trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex)
            event.status = "IGNORED" if old_refund in {"SUCCEEDED", "FAILED"} and old_refund != refund.status else "PROCESSED"
            event.processed_at = utcnow(); db.commit()
            return {"code": 200, "message": "SUCCESS"}

        payment = db.query(PaymentOrder).filter((PaymentOrder.partner_transaction_id == tx) | (PaymentOrder.provider_transaction_id == provider_tx)).first()
        if not payment:
            event.status = "REJECTED"; event.error = "unknown order"; event.processed_at = utcnow(); write_audit(db, actor_id=None, actor_role="system", action="WEBHOOK_REJECTED", resource_type="WebhookEvent", resource_id=event.id, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex, outcome="UNKNOWN_PAYMENT"); db.commit()
            return {"code": 200, "message": "SUCCESS"}
        if Decimal(amount_value) != Decimal(payment.amount) or (currency and currency != payment.currency):
            event.status = "REJECTED"; event.error = "amount_or_currency_mismatch"; event.processed_at = utcnow(); write_audit(db, actor_id=None, actor_role="system", action="WEBHOOK_REJECTED", resource_type="WebhookEvent", resource_id=event.id, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex, outcome="AMOUNT_OR_CURRENCY_MISMATCH"); db.commit()
            return {"code": 200, "message": "SUCCESS"}
        if status_value not in {"INIT", "PENDING", "PROCESSING", "SUCCESS", "FAIL", "FAILED", "CLOSE", "CLOSED", "CANCEL", "AUTH_SUCCESS"}:
            event.status = "REJECTED"; event.error = "unknown_provider_status"; event.processed_at = utcnow(); write_audit(db, actor_id=None, actor_role="system", action="WEBHOOK_REJECTED", resource_type="WebhookEvent", resource_id=event.id, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex, outcome="UNKNOWN_PROVIDER_STATUS"); db.commit()
            return {"code": 200, "message": "SUCCESS"}
        result = ProviderPaymentResult(provider_transaction_id=provider_tx, provider_request_id=str(request_id or payment.provider_request_id), provider_status=status_value, next_action=NextAction("NONE"))
        old = payment.status
        payment_service.apply_observation(db, payment_id=payment.id, result=result, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex, source="webhook")
        event.status = "IGNORED" if old in {"SUCCEEDED", "FAILED", "CANCELLED", "REVIEW_REQUIRED"} and old != payment.status else "PROCESSED"
        event.processed_at = utcnow()
        db.commit()
        return {"code": 200, "message": "SUCCESS"}

    @router.post("/refunds")
    def refund(body: dict[str, Any], request: Request, idempotency_key: str = Header(default="", alias="Idempotency-Key"), principal: Principal = Depends(require_role("finance", "admin")), db: Session = Depends(get_db)):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        try: result = refund_service.create_refund(db, actor_id=principal.actor_id, actor_role=principal.role, payment_id=str(body.get("payment_id", "")), idem_key=idempotency_key, trace_id=trace_id)
        except ConflictError as exc: raise HTTPException(409, str(exc))
        except PermissionError as exc: raise HTTPException(403, str(exc))
        except NotFoundError as exc: raise HTTPException(404, str(exc))
        except ValueError as exc: raise HTTPException(400, str(exc))
        return {"refund_id": result.id, "refund_status": result.status, "payment_id": result.payment_id}

    @router.get("/refunds/{refund_id}")
    def get_refund(refund_id: str, principal: Principal = Depends(require_role("finance", "admin")), db: Session = Depends(get_db)):
        result = db.get(RefundOrder, refund_id)
        if not result: raise HTTPException(404, "refund not found")
        return {"refund_id": result.id, "refund_status": result.status, "provider_status": result.provider_status, "payment_id": result.payment_id, "amount": str(result.amount), "currency": result.currency}

    @router.post("/refunds/{refund_id}/query")
    def query_refund(refund_id: str, request: Request, principal: Principal = Depends(require_role("finance", "admin")), db: Session = Depends(get_db)):
        try: result = refund_service.query_refund(db, refund_id=refund_id, actor_id=principal.actor_id, actor_role=principal.role, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex)
        except NotFoundError as exc: raise HTTPException(404, str(exc))
        return {"refund_id": result.id, "refund_status": result.status, "provider_status": result.provider_status}

    @router.post("/admin/payments/{payment_id}/reconcile")
    def reconcile(payment_id: str, request: Request, principal: Principal = Depends(require_role("admin", "fde")), db: Session = Depends(get_db)):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        try: payment = payment_service.reconcile(db, payment_id=payment_id, actor_id=principal.actor_id, actor_role=principal.role, trace_id=trace_id)
        except NotFoundError as exc: raise HTTPException(404, str(exc))
        return {"payment_id": payment.id, "payment_status": payment.status, "provider_status": payment.provider_status, "reconcile_attempts": payment.reconcile_attempts}

    @router.post("/admin/reconcile-due")
    def reconcile_due(request: Request, principal: Principal = Depends(require_role("admin", "fde")), db: Session = Depends(get_db)):
        rows = reconciliation_service.scan_due(db, trace_id_factory=lambda: request.headers.get("X-Trace-Id") or uuid.uuid4().hex, limit=20)
        return {"count": len(rows), "payments": [{"payment_id": item.id, "payment_status": item.status} for item in rows]}

    @router.get("/admin/provider-calls")
    def provider_calls(principal: Principal = Depends(require_role("admin", "fde")), db: Session = Depends(get_db)):
        rows = db.query(ProviderCallLog).order_by(ProviderCallLog.created_at.desc()).limit(100).all()
        return [{"operation": x.operation, "trace_id": x.trace_id, "provider_request_id": x.provider_request_id, "http_status": x.http_status, "success": x.success, "error_type": x.error_type, "latency_ms": x.latency_ms} for x in rows]

    @router.get("/admin/webhooks")
    def webhook_events(principal: Principal = Depends(require_role("admin", "fde")), db: Session = Depends(get_db)):
        rows = db.query(WebhookEvent).order_by(WebhookEvent.received_at.desc()).limit(100).all()
        return [{"event_type": x.event_type, "provider_event_id": x.provider_event_id, "delivery_fingerprint": x.delivery_fingerprint, "resource_id": x.resource_id, "provider_status": x.provider_status, "amount": str(x.amount) if x.amount is not None else None, "currency": x.currency, "payload_hash": x.payload_hash, "delivery_id": x.delivery_id, "status": x.status, "error": x.error, "received_at": x.received_at, "processed_at": x.processed_at} for x in rows]

    @router.get("/admin/reconciliation")
    def reconciliation_view(principal: Principal = Depends(require_role("admin", "fde")), db: Session = Depends(get_db)):
        rows = db.query(PaymentOrder).order_by(PaymentOrder.updated_at.desc()).limit(100).all()
        return [{"local_order": x.id, "local_status": x.status, "provider_status": x.provider_status, "amount": str(x.amount), "currency": x.currency, "result": ("MATCHED" if x.provider_status and ((x.status == "SUCCEEDED" and x.provider_status == "SUCCESS") or (x.status == "PROCESSING" and x.provider_status == "PENDING")) else "LOCAL_STALE" if x.provider_status else "MANUAL_REVIEW")} for x in rows]

    @router.post("/vcc/agent")
    def vcc_agent(body: VCCAgentRequest, request: Request, principal: Principal = Depends(require_role("finance", "admin")), db: Session = Depends(get_db)):
        if is_unsafe_request(body.message):
            parsed = unsafe_request()
        else:
            try:
                # The parser is untrusted input processing. Any LLM/network/
                # schema failure fails closed into clarification.
                parsed = intent_parser.parse(body.message)
            except Exception:
                parsed = PaymentRequest(vendor="UNKNOWN", amount="", currency="", purpose="", period_days=30, missing_fields=["request"])
        data = parsed.model_dump()
        clarification_question = _clarification_question(parsed)
        if parsed.rejection_reason:
            return {"parsed": data, "budget": None, "approval": None, "application_id": None, "clarification_question": None, "status": "REJECTED_UNSAFE_REQUEST"}
        if parsed.missing_fields:
            return {"parsed": data, "budget": None, "approval": None, "application_id": None, "clarification_question": clarification_question, "status": "NEEDS_CLARIFICATION"}
        amount = Decimal(parsed.amount)
        budget = budget_tool(amount)
        approval = approval_tool(amount)
        if not budget["passed"]: return {"parsed": data, "budget": budget, "approval": approval, "application_id": None, "clarification_question": None, "status": "REJECTED_BUDGET"}
        app = ApprovalService.create_application(db, requester_id=principal.actor_id, vendor=parsed.vendor, purpose=parsed.purpose, amount=amount, currency=parsed.currency, period_days=parsed.period_days, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex)
        return {"parsed": data, "budget": budget, "approval": approval, "application_id": app.id, "clarification_question": None, "status": app.status}

    @router.post("/vcc/{application_id}/approve")
    def approve_vcc(application_id: str, body: VCCApproveRequest, request: Request, principal: Principal = Depends(require_role("approver", "admin")), db: Session = Depends(get_db)):
        try: app = ApprovalService.approve(db, application_id=application_id, approver_id=principal.actor_id, approve=body.approved, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex)
        except ValueError as exc: raise HTTPException(400, str(exc))
        return {"application_id": app.id, "status": app.status, "approval_status": app.approval_status}

    @router.post("/vcc/{application_id}/card")
    def create_card(application_id: str, request: Request, principal: Principal = Depends(require_role("finance", "admin")), db: Session = Depends(get_db)):
        try: app = issuing_service.create_vcc(db, application_id=application_id, actor_id=principal.actor_id, actor_role=principal.role, trace_id=request.headers.get("X-Trace-Id") or uuid.uuid4().hex)
        except PermissionError as exc: raise HTTPException(403, str(exc))
        except ValueError as exc: raise HTTPException(400, str(exc))
        return {"application_id": app.id, "status": app.status, "provider_card_id": app.provider_card_id, "masked_card": app.masked_card}

    @router.get("/vcc/{application_id}")
    def get_vcc(application_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
        app = db.get(VCCApplication, application_id)
        if not app: raise HTTPException(404, "application not found")
        if principal.role == "finance" and app.requester_id != principal.actor_id: raise HTTPException(404, "application not found")
        return {"application_id": app.id, "vendor": app.vendor, "purpose": app.purpose, "amount": str(app.amount), "currency": app.currency, "period_days": app.period, "status": app.status, "approval_status": app.approval_status, "provider_card_id": app.provider_card_id, "masked_card": app.masked_card}

    @router.get("/admin/audit")
    def audit(principal: Principal = Depends(require_role("admin", "fde")), db: Session = Depends(get_db)):
        rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()
        return [{"actor_id": x.actor_id, "actor_role": x.actor_role, "action": x.action, "resource_type": x.resource_type, "resource_id": x.resource_id, "trace_id": x.trace_id, "outcome": x.outcome, "created_at": x.created_at} for x in rows]

    return router
