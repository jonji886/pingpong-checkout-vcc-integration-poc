from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Optional

import httpx

from ...config import settings
from .auth import PingPongAuthProvider
from .base import (
    ProviderAuthError,
    ProviderContractError,
    ProviderPaymentResult,
    ProviderRateLimited,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderRefundResult,
)
from .mappers import map_payment_response, map_refund_response


class PingPongSandboxCheckoutAdapter:
    """PingPong Checkout V4 Hosted ``prePay`` HTTP adapter.

    This POC deliberately uses Hosted mode so it never accepts or forwards
    PAN/CVV. The public V4 API-only ``unifiedPay`` path is a separate product
    contract with different PCI/account prerequisites and is not silently used
    as a fallback.
    """

    CREATE_PATH = "/v4/payment/prePay"
    QUERY_PATH = "/v4/payment/query"
    REFUND_PATH = "/v4/payment/refund"
    REFUND_QUERY_PATH = "/v4/payment/getRefund"

    def __init__(self, *, base_url: Optional[str] = None, auth: Optional[PingPongAuthProvider] = None, client: Optional[httpx.Client] = None, trade_country: Optional[str] = None, shopper_ip: Optional[str] = None, pay_result_url: Optional[str] = None, pay_cancel_url: Optional[str] = None):
        self.base_url = (base_url or settings.pingpong_base_url).rstrip("/")
        self.auth = auth or PingPongAuthProvider(
            settings.pingpong_acc_id,
            settings.pingpong_app_secret,
            settings.pingpong_api_token,
            client_id=settings.pingpong_client_id,
            salt=settings.pingpong_salt,
            sign_type=settings.pingpong_sign_type,
        )
        self.trade_country = settings.pingpong_trade_country if trade_country is None else trade_country
        self.shopper_ip = settings.pingpong_shopper_ip if shopper_ip is None else shopper_ip
        self.pay_result_url = settings.pingpong_pay_result_url if pay_result_url is None else pay_result_url
        self.pay_cancel_url = settings.pingpong_pay_cancel_url if pay_cancel_url is None else pay_cancel_url
        self.client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0, read=15.0, pool=5.0))

    def _post(self, path: str, biz_content: Mapping[str, Any], request_id: str) -> tuple[dict, int]:
        if not self.base_url:
            raise ProviderContractError("PINGPONG_BASE_URL is required")
        try:
            payload = self.auth.sign_v4(biz_content=biz_content)
        except (RuntimeError, ValueError) as exc:
            raise ProviderContractError(str(exc)) from exc
        try:
            response = self.client.post(self.base_url + path, json=payload, headers=self.auth.headers(payload))
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
        self._require_hosted_configuration(notify_url, redirect_url)
        # Hosted prePay is idempotent by the documented merchantTransactionId;
        # provider_request_id remains a local correlation ID in this flow.
        biz_content: dict[str, Any] = {
            "amount": str(amount),
            "currency": currency.upper(),
            "merchantTransactionId": partner_transaction_id,
            "captureDelayHours": 0,
            "notificationUrl": notify_url or settings.pingpong_notify_url,
            "payResultUrl": redirect_url or self.pay_result_url,
            "payCancelUrl": self.pay_cancel_url,
            "shopperIP": self.shopper_ip,
            "goods": [{"name": "AI API credits", "number": "1", "unitPrice": str(amount), "virtualProduct": "Y"}],
        }
        if self.trade_country:
            biz_content["tradeCountry"] = self.trade_country
        data, status = self._post(self.CREATE_PATH, biz_content, provider_request_id)
        return map_payment_response(data, provider_request_id, http_status=status)

    def query_payment(self, *, partner_transaction_id: str, provider_request_id: str) -> ProviderPaymentResult:
        data, status = self._post(self.QUERY_PATH, {"merchantTransactionId": partner_transaction_id}, provider_request_id)
        return map_payment_response(data, provider_request_id, http_status=status)

    def create_refund(self, *, partner_refund_id: str, provider_request_id: str, partner_transaction_id: str, amount: Decimal, currency: str) -> ProviderRefundResult:
        data, status = self._post(self.REFUND_PATH, {"merchantTransactionId": partner_transaction_id, "merchantRefundId": partner_refund_id, "amount": str(amount), "currency": currency.upper(), "notificationUrl": settings.pingpong_notify_url}, provider_request_id)
        return map_refund_response(data, provider_request_id, http_status=status)

    def query_refund(self, *, partner_refund_id: str, partner_transaction_id: str, provider_request_id: str) -> ProviderRefundResult:
        data, status = self._post(self.REFUND_QUERY_PATH, {"merchantRefundId": partner_refund_id, "merchantTransactionId": partner_transaction_id}, provider_request_id)
        return map_refund_response(data, provider_request_id, http_status=status)

    def _require_hosted_configuration(self, notify_url: Optional[str], redirect_url: Optional[str]) -> None:
        missing = []
        if not self.shopper_ip:
            missing.append("PINGPONG_SHOPPER_IP")
        if not (notify_url or settings.pingpong_notify_url):
            missing.append("PINGPONG_NOTIFY_URL")
        if not (redirect_url or self.pay_result_url):
            missing.append("PINGPONG_PAY_RESULT_URL")
        if not self.pay_cancel_url:
            missing.append("PINGPONG_PAY_CANCEL_URL")
        if missing:
            raise ProviderContractError("PingPong Hosted prePay configuration missing: " + ", ".join(missing))


def _retry_after(response: httpx.Response) -> Optional[float]:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
