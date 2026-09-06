"""Authentication boundary for PingPong's current unified APIs.

The public documentation requires an access token plus an RSA/SM2 Base64
signature and a signing-key version.  The public pages do not define a
portable canonicalization algorithm for this repository, so signing is an
explicit infrastructure port instead of a guessed implementation.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class PingPongWebhookVerifier(Protocol):
    def verify(self, *, body: bytes, headers: Mapping[str, str]) -> bool: ...


class PingPongHeaderSigner(Protocol):
    def sign(self, *, method: str, path: str, body: Mapping[str, Any] | None) -> str: ...


class UnavailablePingPongHeaderSigner:
    def sign(self, *, method: str, path: str, body: Mapping[str, Any] | None) -> str:
        raise RuntimeError(
            "PingPong unified API signer is unavailable; inject the configured RSA/SM2 signer"
        )


class UnavailablePingPongWebhookVerifier:
    def verify(self, *, body: bytes, headers: Mapping[str, str]) -> bool:
        raise RuntimeError(
            "PingPong unified webhook verifier is unavailable; inject the configured verifier"
        )


class PingPongUnifiedAuthProvider:
    """Build current unified API headers without exposing secrets to services."""

    def __init__(
        self,
        access_token: str,
        *,
        sign_version: str = "v1",
        signer: PingPongHeaderSigner | None = None,
        on_behalf_of: str = "",
    ):
        self.access_token = access_token
        self.sign_version = sign_version
        self.signer = signer or UnavailablePingPongHeaderSigner()
        self.on_behalf_of = on_behalf_of

    def headers(
        self,
        *,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        signed: bool = True,
    ) -> dict[str, str]:
        if not self.access_token:
            raise RuntimeError("PingPong unified API access token is required")
        result = {
            "Authorization": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.on_behalf_of:
            result["on-behalf-of"] = self.on_behalf_of
        if signed:
            result["sign"] = self.signer.sign(method=method, path=path, body=body)
            result["sign-version"] = self.sign_version
        return result
