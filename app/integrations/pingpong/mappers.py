"""Provider DTO to domain-port mapping."""

from __future__ import annotations

from typing import Any, Mapping

from .base import NextAction, ProviderPaymentResult, ProviderRefundResult
from .checkout_contracts import (
    PingPongPaymentResponse,
    PingPongRefundResponse,
    PingPongV4Envelope,
    PingPongWebhookPayload,
)


def map_payment_response(payload: Mapping[str, Any], fallback_request_id: str, *, http_status: int | None = None) -> ProviderPaymentResult:
    response = PingPongPaymentResponse.from_envelope(PingPongV4Envelope.from_payload(payload))
    status = _normalise_payment_status(response.status, response.code, response.transaction_id)
    is_failure = status in {"FAILED", "FAIL", "CANCEL", "CLOSED", "CLOSE"}
    return ProviderPaymentResult(
        provider_transaction_id=response.transaction_id,
        provider_request_id=response.request_id or fallback_request_id,
        provider_status=status,
        next_action=_map_next_action(response),
        provider_code=response.code,
        failure_code=response.code if is_failure else None,
        failure_message=response.description if is_failure else None,
        http_status=http_status,
    )


def map_refund_response(payload: Mapping[str, Any], fallback_request_id: str, *, http_status: int | None = None) -> ProviderRefundResult:
    response = PingPongRefundResponse.from_envelope(PingPongV4Envelope.from_payload(payload))
    status = _normalise_failure_status(response.status, response.code)
    return ProviderRefundResult(
        provider_refund_id=response.refund_id,
        provider_request_id=response.request_id or fallback_request_id,
        provider_status=status,
        provider_code=response.code,
        http_status=http_status,
    )


def map_webhook(payload: Mapping[str, Any]) -> PingPongWebhookPayload:
    return PingPongWebhookPayload.from_envelope(PingPongV4Envelope.from_payload(payload))


def _map_next_action(response: PingPongPaymentResponse) -> NextAction:
    # ``paymentUrl`` is documented for hosted mode.  The public non-hosted
    # response describes ``action`` as an object but does not define a stable
    # cross-method URL/key enum, so an unknown action is not guessed here.
    biz = response.raw.get("bizContent", {})
    if isinstance(biz, str):
        return NextAction("NONE")
    if isinstance(biz, Mapping) and biz.get("paymentUrl"):
        return NextAction("REDIRECT", url=str(biz["paymentUrl"]))
    action = response.action
    action_type = str(action.get("type", "")).upper() if action else ""
    if action_type in {"REDIRECT", "QR_CODE", "NONE"}:
        return NextAction(
            action_type,
            url=str(action["url"]) if action.get("url") else None,
            qr_payload=str(action["qrPayload"]) if action.get("qrPayload") else None,
        )
    return NextAction("NONE")


def _normalise_payment_status(status: str, code: str | None, transaction_id: str | None) -> str:
    value = status.upper()
    if value == "PROCESSING" and code not in {None, "000000", "001000"} and not transaction_id:
        return "FAILED"
    return value


def _normalise_failure_status(status: str, code: str | None) -> str:
    value = status.upper()
    if value == "PROCESSING" and code not in {None, "000000", "001000"}:
        return "FAILED"
    return value
