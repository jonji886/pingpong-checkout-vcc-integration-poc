from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping


class PingPongAuthProvider:
    """Auth/signing stays in infrastructure; the business service never sees secrets."""

    def __init__(self, app_id: str, app_secret: str = "", api_token: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_token = api_token

    def headers(self, payload: dict[str, Any]) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_token:
            # Checkout V4's current gateway examples carry the credential as
            # the Authorization value; the account's auth provider may add
            # sign/sign-version when that product contract requires it.
            headers["Authorization"] = self.api_token
        # The exact account-specific PingPong signature contract is intentionally not guessed.
        return headers

    def verify_v4_body(self, payload: Mapping[str, Any], secret: str) -> bool:
        """Verify the documented V4 body signature (MD5/SHA256, salt-prefixed sorted fields).

        Account-specific notification wrappers may carry ``bizContent`` as JSON text;
        it is normalized exactly as transmitted for signature verification.
        """
        body = dict(payload)
        received = str(body.pop("sign", ""))
        sign_type = str(body.get("signType") or body.get("sign_type") or "SHA256").upper()
        parts = []
        for key in sorted(body):
            value = body[key]
            if value is None or value == "":
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            parts.append(f"{key}={value}")
        content = secret + "&".join(parts)
        if sign_type == "MD5":
            expected = hashlib.md5(content.encode()).hexdigest().upper()
        elif sign_type == "SHA256":
            expected = hashlib.sha256(content.encode()).hexdigest().upper()
        else:
            return False
        return hmac.compare_digest(expected, received.upper())

    def webhook_valid(self, raw_body: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    @staticmethod
    def canonical_json_hash(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()
