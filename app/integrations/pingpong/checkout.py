from __future__ import annotations

import time
import json
from decimal import Decimal
from typing import Optional

import httpx

from ...config import settings
from .auth import PingPongAuthProvider
from .base import NextAction, ProviderError, ProviderPaymentResult, ProviderRefundResult


class PingPongSandboxCheckoutAdapter:
    """Sandbox-first HTTP adapter. Exact account product fields remain configurable and unverified until credentials exist."""

    def __init__(self, *, base_url: Optional[str] = None, auth: Optional[PingPongAuthProvider] = None, client: Optional[httpx.Client] = None):
        self.base_url = (base_url or settings.pingpong_base_url).rstrip("/")
        self.auth = auth or PingPongAuthProvider(settings.pingpong_app_id, settings.pingpong_app_secret, settings.pingpong_api_token)
        self.client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0, read=15.0, pool=5.0))

    def _post(self, path: str, payload: dict, request_id: str) -> tuple[dict, int]:
        started = time.monotonic()
        try:
            response = self.client.post(self.base_url + path, json=payload, headers=self.auth.headers(payload))
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise ProviderError("provider transport error", retryable=True, error_type="timeout" if isinstance(exc, httpx.TimeoutException) else "connection") from exc
        if response.status_code == 429:
            raise ProviderError("provider rate limited", retryable=True, status_code=429, error_type="rate_limit")
        if response.status_code >= 500:
            raise ProviderError("provider server error", retryable=True, status_code=response.status_code, error_type="server")
        if response.status_code >= 400:
            raise ProviderError("provider request rejected", status_code=response.status_code, error_type="provider_rejection")
        try:
            return response.json(), response.status_code
        except ValueError as exc:
            raise ProviderError("provider returned invalid JSON", error_type="invalid_response") from exc

    @staticmethod
    def _map(data: dict, request_id: str, http_status: int) -> ProviderPaymentResult:
        # Support documented public/ business wrappers without assuming one fixed action URL field.
        biz = data.get("bizContent") if isinstance(data.get("bizContent"), dict) else data.get("data", data)
        if isinstance(biz, str):
            try: biz = json.loads(biz)
            except ValueError: biz = data
        if not isinstance(biz, dict): biz = data
        status = str(biz.get("status") or biz.get("paymentStatus") or biz.get("tradeStatus") or "PENDING").upper()
        tx = biz.get("providerTransactionId") or biz.get("provider_transaction_id") or biz.get("transaction_id") or biz.get("transactionId") or biz.get("paymentId")
        action = biz.get("action") if isinstance(biz.get("action"), dict) else (biz.get("next_action") if isinstance(biz.get("next_action"), dict) else {})
        atype = str(action.get("type") or ("REDIRECT" if action.get("url") or biz.get("paymentUrl") else "NONE")).upper()
        url = action.get("url") or biz.get("paymentUrl")
        return ProviderPaymentResult(tx, str(biz.get("requestId") or biz.get("request_id") or request_id), status, NextAction(atype, url, action.get("qrPayload") or action.get("qr_payload")), http_status=http_status)

    def create_payment(self, *, partner_transaction_id, provider_request_id, amount, currency, user_id, redirect_url=None, notify_url=None):
        payload = {"partner_transaction_id": partner_transaction_id, "request_id": provider_request_id, "amount": str(amount), "currency": currency, "merchant_user_id": user_id}
        if redirect_url: payload["redirect_url"] = redirect_url
        if notify_url: payload["notify_url"] = notify_url
        data, status = self._post("/api/acq/v4/payments/create", payload, provider_request_id)
        return self._map(data, provider_request_id, status)

    def query_payment(self, *, partner_transaction_id, provider_request_id):
        data, status = self._post("/api/acq/v4/payments/query", {"partner_transaction_id": partner_transaction_id, "request_id": provider_request_id}, provider_request_id)
        return self._map(data, provider_request_id, status)

    def create_refund(self, *, partner_refund_id, provider_request_id, partner_transaction_id, amount, currency):
        data, status = self._post("/api/acq/v4/refunds/create", {"partner_refund_id": partner_refund_id, "request_id": provider_request_id, "partner_transaction_id": partner_transaction_id, "amount": str(amount), "currency": currency}, provider_request_id)
        biz = data.get("bizContent") if isinstance(data.get("bizContent"), dict) else data.get("data", data)
        if isinstance(biz, str):
            try: biz = json.loads(biz)
            except ValueError: biz = data
        if not isinstance(biz, dict): biz = data
        return ProviderRefundResult(biz.get("refundId") or biz.get("refund_id") or biz.get("providerRefundId") or biz.get("provider_refund_id"), str(biz.get("requestId") or biz.get("request_id") or provider_request_id), str(biz.get("status") or "PENDING").upper(), http_status=status)

    def query_refund(self, *, partner_refund_id, provider_request_id):
        data, status = self._post("/api/acq/v4/refunds/query", {"partner_refund_id": partner_refund_id, "request_id": provider_request_id}, provider_request_id)
        biz = data.get("bizContent") if isinstance(data.get("bizContent"), dict) else data.get("data", data)
        if isinstance(biz, str):
            try: biz = json.loads(biz)
            except ValueError: biz = data
        if not isinstance(biz, dict): biz = data
        return ProviderRefundResult(biz.get("refundId") or biz.get("refund_id") or biz.get("providerRefundId") or biz.get("provider_refund_id"), str(biz.get("requestId") or biz.get("request_id") or provider_request_id), str(biz.get("status") or "PENDING").upper(), http_status=status)
