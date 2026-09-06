from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Optional

import httpx

from ...config import settings
from .base import (
    ProviderAuthError,
    ProviderContractError,
    ProviderPaymentResult,
    ProviderRateLimited,
    ProviderRefundResult,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
)
from .unified_auth import PingPongUnifiedAuthProvider
from .unified_mappers import map_unified_payment, map_unified_refund, map_unified_session


class PingPongUnifiedCheckoutAdapter:
    """Current unified Checkout V4 adapter.

    Hosted customer action is created through ``sessions/create``. This class
    deliberately does not construct a direct card payment payload, therefore
    it never accepts or sends PAN/CVV.
    """

    CREATE_SESSION_PATH = "/api/acq/v4/sessions/create"
    QUERY_PATH = "/api/acq/v4/payments/query"
    REFUND_PATH = "/api/acq/v4/refunds/create"
    REFUND_QUERY_PATH = "/api/acq/v4/refunds/query"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        auth: Optional[PingPongUnifiedAuthProvider] = None,
        client: Optional[httpx.Client] = None,
        cancel_url: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.pingpong_base_url).rstrip("/")
        self.auth = auth or PingPongUnifiedAuthProvider(
            settings.pingpong_access_token or settings.pingpong_api_token,
            sign_version=settings.pingpong_sign_version,
            on_behalf_of=settings.pingpong_on_behalf_of,
        )
        self.cancel_url = cancel_url if cancel_url is not None else settings.pingpong_pay_cancel_url
        self.client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0, read=15.0, pool=5.0))

    def _post(self, path: str, body: Mapping[str, Any], request_id: str) -> tuple[dict[str, Any], int]:
        if not self.base_url:
            raise ProviderContractError("PINGPONG_BASE_URL is required")
        try:
            headers = self.auth.headers(method="POST", path=path, body=body, signed=True)
        except (RuntimeError, ValueError) as exc:
            raise ProviderContractError(str(exc)) from exc
        try:
            response = self.client.post(self.base_url + path, json=dict(body), headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout() from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailable() from exc
        if response.status_code == 429:
            raise ProviderRateLimited(retry_after=_retry_after(response))
        if response.status_code in {401, 403}:
            raise ProviderAuthError(status_code=response.status_code)
        if response.status_code >= 500:
            raise ProviderUnavailable(status_code=response.status_code)
        if response.status_code >= 400:
            raise ProviderRejected(status_code=response.status_code)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderContractError("PingPong returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise ProviderContractError("PingPong returned a non-object JSON response")
        return data, response.status_code

    def create_payment(self, *, partner_transaction_id: str, provider_request_id: str, amount: Decimal, currency: str, user_id: str, redirect_url: Optional[str] = None, notify_url: Optional[str] = None) -> ProviderPaymentResult:
        body: dict[str, Any] = {
            "request_id": provider_request_id,
            "partner_transaction_id": partner_transaction_id,
            "amount": str(amount),
            "currency": currency.upper(),
            "partner_user_id": user_id,
        }
        if redirect_url or settings.pingpong_pay_result_url:
            body["redirect_url"] = redirect_url or settings.pingpong_pay_result_url
        if notify_url or settings.pingpong_notify_url:
            body["notify_url"] = notify_url or settings.pingpong_notify_url
        if self.cancel_url:
            body["cancel_url"] = self.cancel_url
        data, status = self._post(self.CREATE_SESSION_PATH, body, provider_request_id)
        return map_unified_session(data, provider_request_id, http_status=status)

    def query_payment(self, *, partner_transaction_id: str, provider_request_id: str) -> ProviderPaymentResult:
        data, status = self._post(self.QUERY_PATH, {"request_id": provider_request_id, "partner_transaction_id": partner_transaction_id}, provider_request_id)
        return map_unified_payment(data, provider_request_id, http_status=status)

    def create_refund(self, *, partner_refund_id: str, provider_request_id: str, partner_transaction_id: str, amount: Decimal, currency: str) -> ProviderRefundResult:
        body: dict[str, Any] = {
            "request_id": provider_request_id,
            "partner_transaction_id": partner_transaction_id,
            "partner_refund_id": partner_refund_id,
            "amount": str(amount),
            "currency": currency.upper(),
        }
        if settings.pingpong_notify_url:
            body["notify_url"] = settings.pingpong_notify_url
        data, status = self._post(self.REFUND_PATH, body, provider_request_id)
        return map_unified_refund(data, provider_request_id, http_status=status)

    def query_refund(self, *, partner_refund_id: str, partner_transaction_id: str, provider_request_id: str) -> ProviderRefundResult:
        body = {"request_id": provider_request_id, "partner_transaction_id": partner_transaction_id, "partner_refund_id": partner_refund_id}
        data, status = self._post(self.REFUND_QUERY_PATH, body, provider_request_id)
        return map_unified_refund(data, provider_request_id, http_status=status)


def _retry_after(response: httpx.Response) -> Optional[float]:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
