from __future__ import annotations

import os
from dataclasses import dataclass


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


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./pingpong.db")
    pingpong_mode: str = os.getenv("PINGPONG_MODE", "").lower()
    pingpong_base_url: str = os.getenv("PINGPONG_BASE_URL", "")
    pingpong_app_id: str = os.getenv("PINGPONG_APP_ID", "")
    pingpong_app_secret: str = os.getenv("PINGPONG_APP_SECRET", "")
    pingpong_api_token: str = os.getenv("PINGPONG_API_TOKEN", "")
    pingpong_webhook_secret: str = os.getenv("PINGPONG_WEBHOOK_SECRET", "")
    pingpong_notify_url: str = os.getenv("PINGPONG_NOTIFY_URL", "")
    mock_payment_status: str = os.getenv("MOCK_PAYMENT_STATUS", "PENDING").upper()
    reconcile_after_seconds: int = int(os.getenv("RECONCILE_AFTER_SECONDS", "3600"))
    demo_auth_tokens: str = os.getenv(
        "DEMO_AUTH_TOKENS",
        "dev-token:developer,finance-token:finance,approver-token:approver,admin-token:admin,fde-token:fde",
    )

    def validate(self) -> None:
        if self.pingpong_mode not in {"mock", "sandbox"}:
            raise RuntimeError("PINGPONG_MODE must be explicitly set to mock or sandbox")
        if not self.pingpong_webhook_secret:
            raise RuntimeError("PINGPONG_WEBHOOK_SECRET is required")
        if self.pingpong_mode == "sandbox":
            missing = [
                name
                for name, value in {
                    "PINGPONG_BASE_URL": self.pingpong_base_url,
                    "PINGPONG_APP_ID": self.pingpong_app_id,
                    "PINGPONG_APP_SECRET or PINGPONG_API_TOKEN": self.pingpong_app_secret or self.pingpong_api_token,
                    "PINGPONG_NOTIFY_URL": self.pingpong_notify_url,
                }.items()
                if not value
            ]
            if missing:
                raise RuntimeError("Sandbox configuration missing: " + ", ".join(missing))

    def auth_tokens(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.demo_auth_tokens.split(","):
            if ":" in item:
                token, role = item.split(":", 1)
                result[token.strip()] = role.strip().lower()
        return result


settings = Settings()
