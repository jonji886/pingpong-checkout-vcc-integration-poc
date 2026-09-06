from __future__ import annotations

from decimal import Decimal


def available_balance(posted: Decimal, held: Decimal) -> Decimal:
    value = Decimal(posted) - Decimal(held)
    return value if value >= 0 else Decimal("0")

