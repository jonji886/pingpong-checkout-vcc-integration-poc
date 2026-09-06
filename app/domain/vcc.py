from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

CLOUD_MONTHLY_BUDGET = Decimal("50000.00")
CLOUD_MONTHLY_USED = Decimal("10000.00")


class CardStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class SpendingControl:
    daily_limit: Optional[Decimal] = None
    monthly_limit: Optional[Decimal] = None


@dataclass(frozen=True)
class VirtualCard:
    provider_card_id: str
    status: CardStatus
    masked_card: str
    currency: str
    spending_control: SpendingControl = SpendingControl()


def budget_check(amount: Decimal) -> bool:
    return Decimal(amount) + CLOUD_MONTHLY_USED <= CLOUD_MONTHLY_BUDGET


def approval_required(amount: Decimal) -> bool:
    return Decimal(amount) > Decimal("1000.00")


VCC_TRANSITIONS = {
    "DRAFT": {"PENDING_APPROVAL"},
    "PENDING_APPROVAL": {"APPROVED", "REJECTED"},
    "APPROVED": {"CARD_CREATING"},
    "CARD_CREATING": {"ACTIVE", "FAILED"},
    "ACTIVE": {"CLOSED"},
}


CARD_STATUS_TRANSITIONS = {
    CardStatus.PENDING: {CardStatus.ACTIVE, CardStatus.CLOSED},
    CardStatus.ACTIVE: {CardStatus.FROZEN, CardStatus.CLOSED},
    CardStatus.FROZEN: {CardStatus.ACTIVE, CardStatus.CLOSED},
    CardStatus.CLOSED: set(),
}


def transition_card(current: CardStatus | str, target: CardStatus | str) -> CardStatus:
    current_status = CardStatus(current)
    target_status = CardStatus(target)
    if target_status == current_status:
        return current_status
    if target_status not in CARD_STATUS_TRANSITIONS.get(current_status, set()):
        raise ValueError("invalid virtual card status transition")
    return target_status


def transition_vcc(current: str, target: str) -> str:
    if target not in VCC_TRANSITIONS.get(current, set()):
        raise ValueError("invalid VCC application transition")
    return target
