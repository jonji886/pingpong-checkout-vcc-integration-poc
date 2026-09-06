from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):
    vendor: str
    amount: str
    currency: str
    purpose: str
    period_days: int
    missing_fields: List[str] = Field(default_factory=list)
    rejection_reason: Optional[str] = None
