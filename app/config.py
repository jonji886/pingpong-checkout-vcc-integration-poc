from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


def _load_dotenv() -> None:
    """Tiny dependency-free .env loader for the local POC."""
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./pingpong.db")
    pingpong_mode: str = os.getenv("PINGPONG_MODE", "").lower()
    pingpong_base_url: str = os.getenv("PINGPONG_BASE_URL", "")
    pingpong_acc_id: str = os.getenv("PINGPONG_ACC_ID", "")
    pingpong_client_id: str = os.getenv("PINGPONG_CLIENT_ID", "")
    pingpong_salt: str = os.getenv("PINGPONG_SALT", "")
    pingpong_sign_type: str = os.getenv("PINGPONG_SIGN_TYPE", "SHA256").upper()
    pingpong_app_id: str = os.getenv("PINGPONG_APP_ID", "")
    pingpong_app_secret: str = os.getenv("PINGPONG_APP_SECRET", "")
    pingpong_api_token: str = os.getenv("PINGPONG_API_TOKEN", "")
    pingpong_webhook_secret: str = os.getenv("PINGPONG_WEBHOOK_SECRET", "")
    pingpong_notify_url: str = os.getenv("PINGPONG_NOTIFY_URL", "")
    pingpong_pay_result_url: str = os.getenv("PINGPONG_PAY_RESULT_URL", "")
    pingpong_pay_cancel_url: str = os.getenv("PINGPONG_PAY_CANCEL_URL", "")
    pingpong_trade_country: str = os.getenv("PINGPONG_TRADE_COUNTRY", "")
    pingpong_shopper_ip: str = os.getenv("PINGPONG_SHOPPER_IP", "")
    pingpong_payment_method_type: str = os.getenv("PINGPONG_PAYMENT_METHOD_TYPE", "scheme")
    pingpong_order_terminal: str = os.getenv("PINGPONG_ORDER_TERMINAL", "01")
    llm_enabled: bool = _env_bool("LLM_ENABLED", False)
    llm_provider: str = os.getenv("LLM_PROVIDER", "deepseek").lower()
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    llm_router_model: str = os.getenv("LLM_ROUTER_MODEL", "deepseek-chat")
    llm_router_max_tokens: int = int(os.getenv("LLM_ROUTER_MAX_TOKENS", "512"))
    llm_router_timeout_seconds: float = float(os.getenv("LLM_ROUTER_TIMEOUT_SECONDS", "10"))
    mock_payment_status: str = os.getenv("MOCK_PAYMENT_STATUS", "PENDING").upper()
    reconcile_after_seconds: int = int(os.getenv("RECONCILE_AFTER_SECONDS", "3600"))
    demo_auth_tokens: str = os.getenv(
        "DEMO_AUTH_TOKENS",
        "dev-token:developer,finance-token:finance,approver-token:approver,admin-token:admin,fde-token:fde",
    )

    def validate(self) -> None:
        if self.pingpong_mode not in {"mock", "sandbox"}:
            raise RuntimeError("PINGPONG_MODE must be explicitly set to mock or sandbox")
        if self.pingpong_mode == "mock" and not self.pingpong_webhook_secret:
            raise RuntimeError("PINGPONG_WEBHOOK_SECRET is required")
        if self.pingpong_mode == "sandbox":
            missing = [
                name
                for name, value in {
                    "PINGPONG_BASE_URL": self.pingpong_base_url,
                    "PINGPONG_ACC_ID": self.pingpong_acc_id,
                    "PINGPONG_CLIENT_ID": self.pingpong_client_id,
                    "PINGPONG_SALT": self.pingpong_salt,
                    "PINGPONG_NOTIFY_URL": self.pingpong_notify_url,
                    "PINGPONG_PAY_RESULT_URL": self.pingpong_pay_result_url,
                    "PINGPONG_PAY_CANCEL_URL": self.pingpong_pay_cancel_url,
                    "PINGPONG_SHOPPER_IP": self.pingpong_shopper_ip,
                }.items()
                if not value
            ]
            if missing:
                raise RuntimeError("Sandbox configuration missing: " + ", ".join(missing))
            invalid_urls = [
                name
                for name, value in {
                    "PINGPONG_BASE_URL": self.pingpong_base_url,
                    "PINGPONG_NOTIFY_URL": self.pingpong_notify_url,
                    "PINGPONG_PAY_RESULT_URL": self.pingpong_pay_result_url,
                    "PINGPONG_PAY_CANCEL_URL": self.pingpong_pay_cancel_url,
                }.items()
                if not _is_https_url(value)
            ]
            if invalid_urls:
                raise RuntimeError("Sandbox URL must be a complete HTTPS URL: " + ", ".join(invalid_urls))
        if self.llm_enabled:
            if self.llm_provider != "deepseek":
                raise RuntimeError("LLM_PROVIDER must be deepseek when LLM_ENABLED=true")
            if not self.deepseek_api_key:
                raise RuntimeError("DEEPSEEK_API_KEY is required when LLM_ENABLED=true")
            if not _is_https_url(self.deepseek_base_url):
                raise RuntimeError("DEEPSEEK_BASE_URL must be a complete HTTPS URL")
            if self.llm_router_max_tokens <= 0 or self.llm_router_timeout_seconds <= 0:
                raise RuntimeError("LLM token and timeout settings must be positive")

    def auth_tokens(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.demo_auth_tokens.split(","):
            if ":" in item:
                token, role = item.split(":", 1)
                result[token.strip()] = role.strip().lower()
        return result


settings = Settings()


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    reserved = hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith((".invalid", ".example"))
    return parsed.scheme.lower() == "https" and bool(hostname) and not reserved
