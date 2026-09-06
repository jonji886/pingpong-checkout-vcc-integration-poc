from __future__ import annotations

from typing import Any


SENSITIVE_KEY_PARTS = ("secret", "token", "authorization", "sign", "cvv", "pan", "card_number", "first_name", "last_name", "email", "phone", "ip", "paymenturl", "payment_url", "qr_payload")


def redact(value: Any) -> Any:
    """Return a recursively sanitized copy suitable for logs/snapshots."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key_text = str(key).lower()
            result[key] = "[REDACTED]" if any(part in key_text for part in SENSITIVE_KEY_PARTS) else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


redact_sensitive = redact
