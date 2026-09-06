from __future__ import annotations

import os
from decimal import Decimal
from typing import Dict

from .base import NextAction, ProviderPaymentResult, ProviderRateLimited, ProviderRefundResult, ProviderTimeout


class MockPingPongCheckoutAdapter:
    """Deterministic adapter used for local demo/tests; no claim of Sandbox verification."""

    def __init__(self, status: str | None = None):
        raw_status = status if status is not None else (os.getenv("MOCK_PAYMENT_STATUS") or "PENDING")
        self.status = raw_status.upper()
        self.payments: Dict[str, ProviderPaymentResult] = {}
        self.refunds: Dict[str, ProviderRefundResult] = {}
        self.create_calls = 0
        self.refund_calls = 0
        self.behavior = os.getenv("MOCK_PROVIDER_BEHAVIOR", "")

    def _result(self, partner_transaction_id: str, provider_request_id: str, amount: Decimal) -> ProviderPaymentResult:
        status = self.status
        if status == "TIMEOUT" or partner_transaction_id.endswith("_TIMEOUT") or self.behavior.upper() == "TIMEOUT":
            raise ProviderTimeout()
        if status == "429" or partner_transaction_id.endswith("_429") or self.behavior.upper() == "429":
            raise ProviderRateLimited()
        if status not in {"PENDING", "SUCCESS", "FAIL", "CLOSE", "AUTH_SUCCESS"}:
            status = "PENDING"
        action = NextAction("REDIRECT", "https://mock.invalid/checkout/" + partner_transaction_id) if status in {"PENDING", "AUTH_SUCCESS"} else NextAction("NONE")
        return ProviderPaymentResult("mock_tx_" + partner_transaction_id, provider_request_id, status, action, http_status=200)

    def create_payment(self, *, partner_transaction_id, provider_request_id, amount, currency, user_id, redirect_url=None, notify_url=None):
        self.create_calls += 1
        if partner_transaction_id in self.payments:
            return self.payments[partner_transaction_id]
        result = self._result(partner_transaction_id, provider_request_id, amount)
        self.payments[partner_transaction_id] = result
        return result

    def query_payment(self, *, partner_transaction_id, provider_request_id):
        result = self.payments.get(partner_transaction_id)
        if result is None:
            result = self._result(partner_transaction_id, provider_request_id, Decimal("0"))
            self.payments[partner_transaction_id] = result
        return result

    def create_refund(self, *, partner_refund_id, provider_request_id, partner_transaction_id, amount, currency):
        self.refund_calls += 1
        if partner_refund_id in self.refunds:
            return self.refunds[partner_refund_id]
        if self.status == "TIMEOUT" or self.behavior.upper() == "TIMEOUT":
            raise ProviderTimeout()
        if self.status == "429" or self.behavior.upper() == "429":
            raise ProviderRateLimited()
        status = "SUCCESS" if self.status not in {"FAIL", "TIMEOUT"} else "FAIL"
        result = ProviderRefundResult("mock_rf_" + partner_refund_id, provider_request_id, status, http_status=200)
        self.refunds[partner_refund_id] = result
        return result

    def query_refund(self, *, partner_refund_id, partner_transaction_id, provider_request_id):
        return self.refunds.get(partner_refund_id) or ProviderRefundResult("mock_rf_" + partner_refund_id, provider_request_id, "SUCCESS", http_status=200)

    def set_payment_status(self, partner_transaction_id: str, status: str) -> None:
        old = self.payments.get(partner_transaction_id)
        self.payments[partner_transaction_id] = ProviderPaymentResult(
            old.provider_transaction_id if old else "mock_tx_" + partner_transaction_id,
            old.provider_request_id if old else "req_" + partner_transaction_id,
            status.upper(), NextAction("NONE"), http_status=200,
        )
