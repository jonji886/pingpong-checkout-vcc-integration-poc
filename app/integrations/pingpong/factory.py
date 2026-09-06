from __future__ import annotations

from .mock_checkout import MockPingPongCheckoutAdapter
from .unified_checkout import PingPongUnifiedCheckoutAdapter


def checkout_provider(mode: str):
    if mode == "mock": return MockPingPongCheckoutAdapter()
    if mode == "sandbox": return PingPongUnifiedCheckoutAdapter()
    raise RuntimeError("PINGPONG_MODE must be explicitly set to mock or sandbox")
