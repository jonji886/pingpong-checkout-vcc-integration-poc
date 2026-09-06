from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class TopupRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: str = "USD"

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, value: str) -> str:
        return value.upper()


class NextActionModel(BaseModel):
    type: str
    url: Optional[str] = None
    qr_payload: Optional[str] = None


class TopupResponse(BaseModel):
    payment_id: str
    payment_status: str
    next_action: Optional[NextActionModel] = None


class VCCAgentRequest(BaseModel):
    message: str = Field(min_length=1)


class VCCApproveRequest(BaseModel):
    approved: bool

