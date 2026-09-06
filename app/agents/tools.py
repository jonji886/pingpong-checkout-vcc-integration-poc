from __future__ import annotations

from decimal import Decimal

from ..domain.vcc import approval_required, budget_check


def budget_tool(amount: Decimal) -> dict:
    return {"passed": budget_check(amount), "reason": "within monthly cloud budget" if budget_check(amount) else "monthly cloud budget exceeded"}


def approval_tool(amount: Decimal) -> dict:
    return {"required": approval_required(amount), "reason": "amount exceeds 1,000 USD threshold" if approval_required(amount) else "small expense"}

