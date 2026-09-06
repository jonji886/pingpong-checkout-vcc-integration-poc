from __future__ import annotations

from .checkout import PingPongSandboxCheckoutAdapter
from .mock_checkout import MockPingPongCheckoutAdapter


def checkout_provider(mode: str):
    if mode == "mock": return MockPingPongCheckoutAdapter()
    if mode == "sandbox": return PingPongSandboxCheckoutAdapter()
    raise RuntimeError("PINGPONG_MODE must be explicitly set to mock or sandbox")

