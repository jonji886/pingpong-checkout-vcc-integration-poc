from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from ...domain.vcc import CardStatus, transition_card


class MockPingPongIssuingAdapter:
    """Deterministic local Issuing port; never represents real card data."""

    def __init__(self):
        self.calls = 0
        self.cards: dict[str, dict[str, Any]] = {}

    def create_vcc(self, *, application_id: str, vendor: str, amount: Decimal, currency: str, period_days: int) -> dict[str, Any]:
        return self.create_card(application_id=application_id, vendor=vendor, amount=amount, currency=currency, period_days=period_days)

    def create_card(self, *, application_id: str, vendor: str, amount: Decimal, currency: str, period_days: int) -> dict[str, Any]:
        self.calls += 1
        provider_card_id = "mock_card_" + application_id[-8:]
        result = {
            "provider_card_id": provider_card_id,
            "masked_card": "**** **** **** " + str(abs(hash(application_id)) % 10000).zfill(4),
            "status": CardStatus.ACTIVE.value,
            "currency": currency,
            "spending_control": {"daily_limit": None, "monthly_limit": None},
            "vendor": vendor,
            "amount": str(amount),
            "period_days": period_days,
        }
        self.cards[provider_card_id] = result
        return result

    def get_card(self, *, provider_card_id: str) -> dict[str, Any]:
        if provider_card_id not in self.cards:
            raise ValueError("mock card not found")
        return dict(self.cards[provider_card_id])

    def change_card_status(self, *, provider_card_id: str, action: str) -> dict[str, Any]:
        card = self.get_card(provider_card_id=provider_card_id)
        action_map = {"FREEZE": CardStatus.FROZEN, "UNFREEZE": CardStatus.ACTIVE, "CLOSE": CardStatus.CLOSED}
        if action.upper() not in action_map:
            raise ValueError("unsupported mock card action")
        card["status"] = transition_card(card["status"], action_map[action.upper()]).value
        self.cards[provider_card_id] = card
        return dict(card)

    def update_spending_control(self, *, provider_card_id: str, controls: Mapping[str, Any]) -> dict[str, Any]:
        card = self.get_card(provider_card_id=provider_card_id)
        card["spending_control"] = {key: str(value) for key, value in controls.items() if key in {"daily_limit", "monthly_limit"}}
        self.cards[provider_card_id] = card
        return dict(card)

    def get_balance(self, *, provider_card_id: str) -> dict[str, Any]:
        card = self.get_card(provider_card_id=provider_card_id)
        return {"provider_card_id": provider_card_id, "currency": card["currency"], "available": "0.00", "source": "mock"}

    def query_transactions(self, *, provider_card_id: str, page_no: int = 1, page_size: int = 20) -> dict[str, Any]:
        self.get_card(provider_card_id=provider_card_id)
        return {"total": 0, "transactions": [], "page_no": page_no, "page_size": page_size, "source": "mock"}
