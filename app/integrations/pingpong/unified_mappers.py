"""Current unified provider DTO to domain-port mapping."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .base import NextAction, ProviderPaymentResult, ProviderRefundResult
from .checkout_contracts import PingPongWebhookPayload
from .unified_contracts import (
    PingPongIssuingResponse,
    PingPongUnifiedPaymentResponse,
    PingPongUnifiedRefundResponse,
    PingPongUnifiedResponse,
    require_success,
)


def _payment_status(value: str | None, *, session: bool = False) -> str:
    # A successfully created Checkout Session is not a successful payment.
    return "PROCESSING" if session and not value else (value or "PROCESSING").upper()


def map_unified_session(payload: Mapping[str, Any], fallback_request_id: str, *, http_status: int | None = None) -> ProviderPaymentResult:
    envelope = PingPongUnifiedResponse.from_payload(payload)
    require_success(envelope)
    data = PingPongUnifiedPaymentResponse.from_response(envelope)
    action_url = data.action.get("redirect_url")
    return ProviderPaymentResult(
        provider_transaction_id=data.transaction_id,
        provider_request_id=data.request_id or fallback_request_id,
        provider_status=_payment_status(data.status, session=True),
        next_action=NextAction("REDIRECT", url=str(action_url)) if action_url else NextAction("NONE"),
        provider_code=data.result_code or envelope.code,
        failure_message=data.result_message,
        http_status=http_status,
    )


def map_unified_payment(payload: Mapping[str, Any], fallback_request_id: str, *, http_status: int | None = None) -> ProviderPaymentResult:
    envelope = PingPongUnifiedResponse.from_payload(payload)
    require_success(envelope)
    data = PingPongUnifiedPaymentResponse.from_response(envelope)
    status = _payment_status(data.status)
    failed = status in {"FAIL", "FAILED", "CANCEL", "CLOSED", "CLOSE"}
    return ProviderPaymentResult(
        provider_transaction_id=data.transaction_id,
        provider_request_id=data.request_id or fallback_request_id,
        provider_status=status,
        next_action=_map_action(data.action),
        provider_code=data.result_code or envelope.code,
        failure_code=(data.result_code or envelope.code) if failed else None,
        failure_message=data.result_message if failed else None,
        http_status=http_status,
    )


def map_unified_refund(payload: Mapping[str, Any], fallback_request_id: str, *, http_status: int | None = None) -> ProviderRefundResult:
    envelope = PingPongUnifiedResponse.from_payload(payload)
    require_success(envelope)
    data = PingPongUnifiedRefundResponse.from_response(envelope)
    return ProviderRefundResult(
        provider_refund_id=data.refund_id,
        provider_request_id=data.request_id or fallback_request_id,
        provider_status=(data.status or "PROCESSING").upper(),
        provider_code=data.result_code or envelope.code,
        http_status=http_status,
    )


def map_issuing_card(payload: Mapping[str, Any]) -> dict[str, Any]:
    response = PingPongIssuingResponse.from_payload(payload)
    require_success(response)
    card_id = response.data.get("card_id")
    if not card_id:
        raise ValueError("PingPong issuing response did not contain card_id")
    return {"provider_card_id": str(card_id), "source": "pingpong_unified"}


def map_issuing_detail(payload: Mapping[str, Any]) -> dict[str, Any]:
    response = PingPongIssuingResponse.from_payload(payload)
    require_success(response)
    data = response.data
    status = str(data.get("card_status") or "INACTIVE").upper()
    domain_status = {"ACTIVE": "ACTIVE", "INACTIVE": "PENDING", "REVOKED": "CLOSED", "CANCELED": "CLOSED"}.get(status)
    if domain_status is None:
        raise ValueError("unknown PingPong issuing card status")
    card_number = str(data.get("card_number") or "")
    masked = card_number if "*" in card_number else ("**** **** **** " + card_number[-4:] if card_number else "")
    return {
        "provider_card_id": str(data.get("card_id") or ""),
        "status": domain_status,
        "masked_card": masked,
        "currency": str(data.get("billing_currency") or "").upper(),
        # PAN/CVC are intentionally not returned across the port boundary.
    }


def map_issuing_action(payload: Mapping[str, Any], *, provider_card_id: str) -> dict[str, Any]:
    response = PingPongIssuingResponse.from_payload(payload)
    require_success(response)
    return {"provider_card_id": provider_card_id, "code": response.code, "source": "pingpong_unified"}


def map_issuing_transactions(payload: Mapping[str, Any]) -> dict[str, Any]:
    response = PingPongIssuingResponse.from_payload(payload)
    require_success(response)
    data = response.data
    # Return the documented list under a stable adapter key; fields remain
    # provider-shaped inside this read-only reconciliation result.
    return {"total": data.get("total_num", 0), "transactions": data.get("list", [])}


def map_unified_webhook(payload: Mapping[str, Any]) -> PingPongWebhookPayload:
    """Map the current flat Checkout webhook payload, not the legacy envelope."""
    if not isinstance(payload, Mapping):
        raise ValueError("PingPong unified webhook must be an object")
    refund_id = _first_value(payload, "refund_id", "refundId")
    partner_refund_id = _first_value(payload, "partner_refund_id", "partnerRefundId")
    event_name = str(_first_value(payload, "event", "event_name", "eventName", "type") or "").lower()
    is_refund = "refund" in event_name or refund_id is not None or partner_refund_id is not None
    return PingPongWebhookPayload(
        event_type="refund" if is_refund else "payment",
        merchant_transaction_id=_first_value(payload, "partner_transaction_id", "partnerTransactionId"),
        transaction_id=_first_value(payload, "transaction_id", "transactionId"),
        merchant_refund_id=partner_refund_id,
        refund_id=refund_id,
        request_id=_first_value(payload, "request_id", "requestId"),
        amount=_decimal_value(payload.get("amount")),
        currency=_upper_value(payload.get("currency")),
        status=str(payload.get("status") or ""),
        notify_type=_upper_value(_first_value(payload, "event", "event_name", "eventName", "type")),
        raw=dict(payload),
    )


def _map_action(action: Mapping[str, Any]) -> NextAction:
    redirect_url = action.get("redirect_url")
    qr_url = action.get("qr_url") or action.get("qr_code")
    if redirect_url:
        return NextAction("REDIRECT", url=str(redirect_url))
    if qr_url:
        return NextAction("QR_CODE", qr_payload=str(qr_url))
    return NextAction("NONE")


def _first_value(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _upper_value(value: Any) -> str | None:
    return value.upper() if isinstance(value, str) and value else None


def _decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("PingPong unified webhook amount is not a decimal") from exc
