from __future__ import annotations

from decimal import Decimal


CLOUD_MONTHLY_BUDGET = Decimal("50000.00")
CLOUD_MONTHLY_USED = Decimal("10000.00")


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


def transition_vcc(current: str, target: str) -> str:
    if target not in VCC_TRANSITIONS.get(current, set()):
        raise ValueError("invalid VCC application transition")
    return target
