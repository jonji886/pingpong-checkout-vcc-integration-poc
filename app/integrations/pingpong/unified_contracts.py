"""DTOs for the current PingPong unified Checkout and Issuing contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from .base import ProviderContractError, ProviderRejected


def _str(value: Any) -> Optional[str]:
    return None if value in (None, "") else str(value)


def _decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderContractError("PingPong amount is not a decimal") from exc


def _object(value: Any) -> Mapping[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class PingPongUnifiedResponse:
    code: Optional[str]
    message: Optional[str]
    data: Mapping[str, Any]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PingPongUnifiedResponse":
        if not isinstance(payload, Mapping):
            raise ProviderContractError("PingPong unified response must be an object")
        data = payload.get("data", {})
        if data is None:
            data = {}
        if not isinstance(data, Mapping):
            raise ProviderContractError("PingPong unified response data must be an object")
        return cls(_str(payload.get("code")), _str(payload.get("message")), dict(data), dict(payload))


@dataclass(frozen=True)
class PingPongUnifiedPaymentResponse:
    request_id: Optional[str]
    partner_transaction_id: Optional[str]
    transaction_id: Optional[str]
    amount: Optional[Decimal]
    currency: Optional[str]
    status: Optional[str]
    action: Mapping[str, Any]
    result_code: Optional[str]
    result_message: Optional[str]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_response(cls, response: PingPongUnifiedResponse) -> "PingPongUnifiedPaymentResponse":
        data = response.data
        return cls(
            request_id=_str(data.get("request_id")),
            partner_transaction_id=_str(data.get("partner_transaction_id")),
            transaction_id=_str(data.get("transaction_id")),
            amount=_decimal(data.get("amount")),
            currency=(_str(data.get("currency")) or "").upper() or None,
            status=(_str(data.get("status")) or "").upper() or None,
            action=_object(data.get("action")),
            result_code=_str(data.get("result_code")),
            result_message=_str(data.get("result_message")) or response.message,
            raw=response.raw,
        )


@dataclass(frozen=True)
class PingPongUnifiedRefundResponse:
    request_id: Optional[str]
    partner_transaction_id: Optional[str]
    transaction_id: Optional[str]
    partner_refund_id: Optional[str]
    refund_id: Optional[str]
    amount: Optional[Decimal]
    currency: Optional[str]
    status: Optional[str]
    result_code: Optional[str]
    result_message: Optional[str]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_response(cls, response: PingPongUnifiedResponse) -> "PingPongUnifiedRefundResponse":
        data = response.data
        return cls(
            request_id=_str(data.get("request_id")),
            partner_transaction_id=_str(data.get("partner_transaction_id")),
            transaction_id=_str(data.get("transaction_id")),
            partner_refund_id=_str(data.get("partner_refund_id")),
            refund_id=_str(data.get("refund_id")),
            amount=_decimal(data.get("amount")),
            currency=(_str(data.get("currency")) or "").upper() or None,
            status=(_str(data.get("status")) or "").upper() or None,
            result_code=_str(data.get("result_code")),
            result_message=_str(data.get("result_message")) or response.message,
            raw=response.raw,
        )


@dataclass(frozen=True)
class PingPongIssuingResponse:
    code: Optional[str]
    data: Mapping[str, Any]
    message: Optional[str]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PingPongIssuingResponse":
        response = PingPongUnifiedResponse.from_payload(payload)
        return cls(response.code, response.data, response.message, response.raw)


def require_success(response: PingPongUnifiedResponse | PingPongIssuingResponse) -> None:
    if response.code not in (None, "", "SUCCESS", "200"):
        raise ProviderRejected(
            "PingPong returned an unsuccessful response: " + str(response.code)
        )
