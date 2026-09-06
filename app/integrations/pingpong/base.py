from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional, Protocol


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, status_code: Optional[int] = None, error_type: str = "provider"):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.error_type = error_type


class ProviderUnavailable(ProviderError):
    def __init__(self, message: str = "provider unavailable", *, status_code: Optional[int] = None):
        super().__init__(message, retryable=True, status_code=status_code, error_type="unavailable")


class ProviderRejected(ProviderError):
    def __init__(self, message: str = "provider rejected request", *, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, error_type="provider_rejected")


class ProviderAuthError(ProviderError):
    def __init__(self, message: str = "provider authentication failed", *, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, error_type="provider_auth")


class ProviderContractError(ProviderError):
    def __init__(self, message: str = "provider contract error"):
        super().__init__(message, error_type="contract")


class ProviderTimeout(ProviderError):
    def __init__(self, message: str = "provider timeout"):
        super().__init__(message, retryable=True, error_type="timeout")


class ProviderRateLimited(ProviderError):
    def __init__(self, message: str = "provider rate limited", *, retry_after: Optional[float] = None):
        super().__init__(message, retryable=True, status_code=429, error_type="rate_limit")
        self.retry_after = retry_after


@dataclass(frozen=True)
class NextAction:
    type: str
    url: Optional[str] = None
    qr_payload: Optional[str] = None


@dataclass(frozen=True)
class ProviderPaymentResult:
    provider_transaction_id: Optional[str]
    provider_request_id: str
    provider_status: str
    next_action: NextAction
    provider_code: Optional[str] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    http_status: Optional[int] = None


@dataclass(frozen=True)
class ProviderRefundResult:
    provider_refund_id: Optional[str]
    provider_request_id: str
    provider_status: str
    provider_code: Optional[str] = None
    http_status: Optional[int] = None


class CheckoutProvider(Protocol):
    def create_payment(self, *, partner_transaction_id: str, provider_request_id: str, amount: Decimal, currency: str, user_id: str, redirect_url: Optional[str] = None, notify_url: Optional[str] = None) -> ProviderPaymentResult: ...
    def query_payment(self, *, partner_transaction_id: str, provider_request_id: str) -> ProviderPaymentResult: ...
    def create_refund(self, *, partner_refund_id: str, provider_request_id: str, partner_transaction_id: str, amount: Decimal, currency: str) -> ProviderRefundResult: ...
    def query_refund(self, *, partner_refund_id: str, partner_transaction_id: str, provider_request_id: str) -> ProviderRefundResult: ...


class IssuingProvider(Protocol):
    def create_vcc(self, *, application_id: str, vendor: str, amount: Decimal, currency: str, period_days: int) -> dict[str, Any]: ...
    def create_card(self, *, application_id: str, vendor: str, amount: Decimal, currency: str, period_days: int) -> dict[str, Any]: ...
    def get_card(self, *, provider_card_id: str) -> dict[str, Any]: ...
    def change_card_status(self, *, provider_card_id: str, action: str) -> dict[str, Any]: ...
    def update_spending_control(self, *, provider_card_id: str, controls: Mapping[str, Any]) -> dict[str, Any]: ...
    def get_balance(self, *, provider_card_id: str) -> dict[str, Any]: ...
