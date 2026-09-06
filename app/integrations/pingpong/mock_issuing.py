from __future__ import annotations

from decimal import Decimal


class MockPingPongIssuingAdapter:
    def __init__(self):
        self.calls = 0

    def create_vcc(self, *, application_id: str, vendor: str, amount: Decimal, currency: str, period_days: int) -> dict:
        self.calls += 1
        suffix = application_id[-8:]
        return {"provider_card_id": "mock_card_" + suffix, "masked_card": "**** **** **** " + str(abs(hash(application_id)) % 10000).zfill(4)}

