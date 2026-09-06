"""PingPong Issuing provider adapters."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Optional
from urllib.parse import urlencode

import httpx

from ...config import settings
from .base import (
    IssuingProvider,
    ProviderAuthError,
    ProviderContractError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
)
from .mock_issuing import MockPingPongIssuingAdapter
from .unified_auth import PingPongUnifiedAuthProvider
from .unified_contracts import PingPongIssuingResponse
from .unified_mappers import map_issuing_action, map_issuing_card, map_issuing_detail, map_issuing_transactions


class PingPongIssuingHttpAdapter(IssuingProvider):
    """Current public PingPong Issuing v2 HTTP adapter.

    Card product eligibility and the RSA/SM2 signing implementation are
    explicit infrastructure inputs. No guessed product code or signature
    algorithm is embedded here.
    """

    CREATE_CARD_PATH = "/api/issuing/card/v2/apply"
    CARD_DETAIL_PATH = "/api/issuing/card/v2/detail"
    FREEZE_PATH = "/api/issuing/card/v2/freeze"
    UNFREEZE_PATH = "/api/issuing/card/v2/unfreeze"
    CLOSE_PATH = "/api/issuing/card/v2/close"
    SPENDING_CONTROL_PATH = "/api/issuing/spending-control/v2/share-card-limit"
    BALANCE_PATH = "/api/issuing/card/v2/normal/balance"
    AUTHORIZATION_LOG_PATH = "/api/issuing/transaction/v2/authorizations"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        auth: Optional[PingPongUnifiedAuthProvider] = None,
        card_product_code: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ):
        self.base_url = (base_url or settings.pingpong_base_url).rstrip("/")
        self.auth = auth or PingPongUnifiedAuthProvider(
            settings.pingpong_access_token or settings.pingpong_api_token,
            sign_version=settings.pingpong_sign_version,
            on_behalf_of=settings.pingpong_on_behalf_of,
        )
        self.card_product_code = card_product_code if card_product_code is not None else settings.pingpong_issuing_card_product_code
        self.client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0, read=15.0, pool=5.0))

    def create_vcc(self, *, application_id: str, vendor: str, amount: Decimal, currency: str, period_days: int) -> dict[str, Any]:
        return self.create_card(application_id=application_id, vendor=vendor, amount=amount, currency=currency, period_days=period_days)

    def create_card(self, *, application_id: str, vendor: str, amount: Decimal, currency: str, period_days: int) -> dict[str, Any]:
        if not self.card_product_code:
            raise ProviderContractError("PINGPONG_ISSUING_CARD_PRODUCT_CODE is required")
        # period_days is a DemoAI workflow field. The public create-card v2
        # contract has no validity-period field, so it is not serialized.
        body = {
            "card_product_code": self.card_product_code,
            "remark": vendor[:128],
            "transaction_amount_limit": str(amount),
            "lifetime_limit": str(amount),
            "apply_coupon": False,
        }
        payload, _ = self._request("POST", self.CREATE_CARD_PATH, body=body, signed=True)
        result = map_issuing_card(payload)
        result.update({"status": "PENDING", "masked_card": ""})
        return result

    def get_card(self, *, provider_card_id: str) -> dict[str, Any]:
        payload, _ = self._request("GET", self.CARD_DETAIL_PATH, params={"card_id": provider_card_id}, signed=False)
        return map_issuing_detail(payload)

    def change_card_status(self, *, provider_card_id: str, action: str) -> dict[str, Any]:
        paths = {"FREEZE": self.FREEZE_PATH, "UNFREEZE": self.UNFREEZE_PATH, "CLOSE": self.CLOSE_PATH}
        path = paths.get(action.upper())
        if path is None:
            raise ProviderContractError("unsupported PingPong card action")
        payload, _ = self._request("POST", path, body={"card_id": provider_card_id}, signed=True)
        return map_issuing_action(payload, provider_card_id=provider_card_id)

    def update_spending_control(self, *, provider_card_id: str, controls: Mapping[str, Any]) -> dict[str, Any]:
        type_map = {"daily_limit": "DAY", "monthly_limit": "MONTH", "lifetime_limit": "LIFETIME", "transaction_limit": "TRANSACTION"}
        results = []
        for key, value in controls.items():
            if key not in type_map:
                continue
            payload, _ = self._request(
                "POST",
                self.SPENDING_CONTROL_PATH,
                body={"card_id": provider_card_id, "spending_limit": str(value), "limit_type": type_map[key]},
                signed=True,
            )
            response = PingPongIssuingResponse.from_payload(payload)
            self._require_success(response)
            results.append(response.code)
        return {"provider_card_id": provider_card_id, "updated": results, "source": "pingpong_unified"}

    def get_balance(self, *, provider_card_id: str) -> dict[str, Any]:
        payload, _ = self._request("GET", self.BALANCE_PATH, params={"card_id": provider_card_id}, signed=False)
        response = PingPongIssuingResponse.from_payload(payload)
        self._require_success(response)
        return {"provider_card_id": provider_card_id, "available_balance": response.data.get("available_balance"), "source": "pingpong_unified"}

    def query_transactions(self, *, provider_card_id: str, page_no: int = 1, page_size: int = 20) -> dict[str, Any]:
        payload, _ = self._request(
            "GET",
            self.AUTHORIZATION_LOG_PATH,
            params={"card_id": provider_card_id, "page_no": page_no, "page_size": page_size},
            signed=False,
        )
        return map_issuing_transactions(payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Mapping[str, Any]] = None,
        params: Optional[Mapping[str, Any]] = None,
        signed: bool,
    ) -> tuple[dict[str, Any], int]:
        if not self.base_url:
            raise ProviderContractError("PINGPONG_BASE_URL is required")
        try:
            headers = self.auth.headers(method=method, path=path, body=body, signed=signed)
        except (RuntimeError, ValueError) as exc:
            raise ProviderContractError(str(exc)) from exc
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        try:
            response = self.client.request(method, url, json=dict(body) if body is not None else None, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout() from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailable() from exc
        if response.status_code == 429:
            raise ProviderRateLimited()
        if response.status_code in {401, 403}:
            raise ProviderAuthError(status_code=response.status_code)
        if response.status_code >= 500:
            raise ProviderUnavailable(status_code=response.status_code)
        if response.status_code >= 400:
            raise ProviderRejected(status_code=response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderContractError("PingPong issuing response is not JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderContractError("PingPong issuing response must be an object")
        return payload, response.status_code

    @staticmethod
    def _require_success(response: PingPongIssuingResponse) -> None:
        if response.code not in (None, "", "SUCCESS", "200"):
            raise ProviderRejected(response.message or "PingPong issuing request rejected")


__all__ = ["MockPingPongIssuingAdapter", "PingPongIssuingHttpAdapter"]
