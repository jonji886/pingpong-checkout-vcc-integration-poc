"""PingPong Checkout V4 provider-side contracts.

The provider envelope is deliberately kept separate from the domain result
types in ``base.py``.  Unknown provider fields are retained in ``raw`` for
diagnostics, but the mapper only consumes fields documented by PingPong's
public Checkout V4 pages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from .base import ProviderContractError


@dataclass(frozen=True)
class PingPongV4Envelope:
    acc_id: Optional[str]
    client_id: Optional[str]
    code: Optional[str]
    description: Optional[str]
    sign_type: Optional[str]
    sign: Optional[str]
    biz_content: Mapping[str, Any]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PingPongV4Envelope":
        if not isinstance(payload, Mapping):
            raise ProviderContractError("PingPong response must be a JSON object")
        raw_biz = payload.get("bizContent", {})
        if isinstance(raw_biz, str):
            try:
                biz = json.loads(raw_biz)
            except (TypeError, ValueError) as exc:
                raise ProviderContractError("PingPong bizContent is not valid JSON") from exc
        else:
            biz = raw_biz
        if not isinstance(biz, Mapping):
            raise ProviderContractError("PingPong bizContent must be an object")
        return cls(
            acc_id=_optional_str(payload.get("accId")),
            client_id=_optional_str(payload.get("clientId")),
            code=_optional_str(payload.get("code")),
            description=_optional_str(payload.get("description")),
            sign_type=_optional_str(payload.get("signType")),
            sign=_optional_str(payload.get("sign")),
            biz_content=dict(biz),
            raw=dict(payload),
        )


@dataclass(frozen=True)
class PingPongPaymentResponse:
    transaction_id: Optional[str]
    merchant_transaction_id: Optional[str]
    request_id: Optional[str]
    amount: Optional[Decimal]
    currency: Optional[str]
    status: str
    action: Mapping[str, Any]
    code: Optional[str]
    description: Optional[str]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_envelope(cls, envelope: PingPongV4Envelope) -> "PingPongPaymentResponse":
        biz = envelope.biz_content
        return cls(
            transaction_id=_first_str(biz, "transactionId"),
            merchant_transaction_id=_first_str(biz, "merchantTransactionId"),
            request_id=_first_str(biz, "requestId"),
            amount=_decimal_or_none(biz.get("amount")),
            currency=_upper_or_none(biz.get("currency")),
            status=_first_str(biz, "status") or "PROCESSING",
            action=_mapping_or_empty(biz.get("action")),
            code=envelope.code,
            description=envelope.description,
            raw=envelope.raw,
        )


@dataclass(frozen=True)
class PingPongRefundResponse:
    transaction_id: Optional[str]
    merchant_transaction_id: Optional[str]
    refund_id: Optional[str]
    merchant_refund_id: Optional[str]
    request_id: Optional[str]
    amount: Optional[Decimal]
    currency: Optional[str]
    status: str
    code: Optional[str]
    description: Optional[str]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_envelope(cls, envelope: PingPongV4Envelope) -> "PingPongRefundResponse":
        biz = envelope.biz_content
        return cls(
            transaction_id=_first_str(biz, "transactionId"),
            merchant_transaction_id=_first_str(biz, "merchantTransactionId"),
            refund_id=_first_str(biz, "refundId"),
            merchant_refund_id=_first_str(biz, "merchantRefundId"),
            request_id=_first_str(biz, "requestId"),
            amount=_decimal_or_none(biz.get("amount")),
            currency=_upper_or_none(biz.get("currency")),
            status=_first_str(biz, "status") or "PROCESSING",
            code=envelope.code,
            description=envelope.description,
            raw=envelope.raw,
        )


@dataclass(frozen=True)
class PingPongWebhookPayload:
    event_type: str
    merchant_transaction_id: Optional[str]
    transaction_id: Optional[str]
    merchant_refund_id: Optional[str]
    refund_id: Optional[str]
    request_id: Optional[str]
    amount: Optional[Decimal]
    currency: Optional[str]
    status: str
    notify_type: Optional[str]
    raw: Mapping[str, Any] = field(repr=False)

    @property
    def is_refund(self) -> bool:
        return self.event_type == "refund"

    @classmethod
    def from_envelope(cls, envelope: PingPongV4Envelope) -> "PingPongWebhookPayload":
        biz = envelope.biz_content
        notify_type = _upper_or_none(biz.get("notifyType"))
        is_refund = notify_type == "REFUND" or bool(
            _first_str(biz, "merchantRefundId") or _first_str(biz, "refundId")
        )
        return cls(
            event_type="refund" if is_refund else "payment",
            merchant_transaction_id=_first_str(biz, "merchantTransactionId"),
            transaction_id=_first_str(biz, "transactionId"),
            merchant_refund_id=_first_str(biz, "merchantRefundId"),
            refund_id=_first_str(biz, "refundId"),
            request_id=_first_str(biz, "requestId"),
            amount=_decimal_or_none(biz.get("amount")),
            currency=_upper_or_none(biz.get("currency")),
            status=_first_str(biz, "status") or "",
            notify_type=notify_type,
            raw=envelope.raw,
        )


def _optional_str(value: Any) -> Optional[str]:
    return str(value) if value not in (None, "") else None


def _first_str(mapping: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = _optional_str(mapping.get(key))
        if value is not None:
            return value
    return None


def _upper_or_none(value: Any) -> Optional[str]:
    result = _optional_str(value)
    return result.upper() if result else None


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderContractError("PingPong amount is not a decimal") from exc


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
