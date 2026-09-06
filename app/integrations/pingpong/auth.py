from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping, Protocol


class SignatureHeaders(Protocol):
    def sign(self, body: Mapping[str, Any]) -> dict[str, Any]: ...


class PingPongSigner(Protocol):
    def sign(self, body: Mapping[str, Any]) -> dict[str, Any]: ...


class UnavailableSigner:
    """Explicit failure object for an adapter without a verified salt."""

    def sign(self, body: Mapping[str, Any]) -> dict[str, Any]:
        raise RuntimeError("PingPong V4 signer is unavailable: configure PINGPONG_SALT")


class VerifiedPingPongSigner:
    """PingPong Checkout V4 MD5/SHA256 signer from the public guide."""

    def __init__(self, salt: str, sign_type: str = "SHA256"):
        if not salt:
            raise ValueError("PingPong V4 salt is required")
        self.salt = salt
        self.sign_type = sign_type.upper()
        if self.sign_type not in {"MD5", "SHA256"}:
            raise ValueError("PingPong V4 sign type must be MD5 or SHA256")

    def sign(self, body: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(body)
        result["signType"] = self.sign_type
        result.pop("sign", None)
        canonical = _canonical_public_body(result)
        digest = hashlib.md5 if self.sign_type == "MD5" else hashlib.sha256
        result["sign"] = digest((self.salt + canonical).encode("utf-8")).hexdigest().upper()
        return result


class PingPongAuthProvider:
    """Auth/signing stays in infrastructure; the business service never sees secrets."""

    def __init__(self, app_id: str, app_secret: str = "", api_token: str = "", *, client_id: str = "", salt: str = "", sign_type: str = "SHA256"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_token = api_token
        self.client_id = client_id
        self.signer: PingPongSigner = VerifiedPingPongSigner(salt, sign_type) if salt else UnavailableSigner()

    def headers(self, payload: dict[str, Any] | None = None) -> dict[str, str]:
        # V4's public guide places authentication/signature fields in the JSON
        # envelope.  We do not invent an Authorization header for this product.
        return {"Content-Type": "application/json", "Accept": "application/json"}

    def sign_v4(self, *, biz_content: Mapping[str, Any], version: str = "1.0") -> dict[str, Any]:
        if not self.app_id or not self.client_id:
            raise RuntimeError("PingPong V4 accId and clientId are required")
        envelope = {
            "accId": self.app_id,
            "clientId": self.client_id,
            "signType": getattr(self.signer, "sign_type", "SHA256"),
            "version": version,
            "bizContent": json.dumps(dict(biz_content), separators=(",", ":"), ensure_ascii=False),
        }
        return self.signer.sign(envelope)

    def verify_v4_body(self, payload: Mapping[str, Any], secret: str) -> bool:
        """Verify the documented V4 full-message signature."""
        body = dict(payload)
        received = str(body.pop("sign", ""))
        sign_type = str(body.get("signType") or body.get("sign_type") or "SHA256").upper()
        content = secret + _canonical_public_body(body)
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


def _canonical_public_body(body: Mapping[str, Any]) -> str:
    parts = []
    for key in sorted(body):
        value = body[key]
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        parts.append(f"{key}={value}")
    return "&".join(parts)
