from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class VCCRequest(BaseModel):
    """Untrusted parser output; policy fields are intentionally absent."""

    model_config = ConfigDict(extra="forbid")
    vendor: str
    amount: str
    currency: str
    purpose: str
    period_days: int
    missing_fields: List[str] = Field(default_factory=list)
    rejection_reason: Optional[str] = None


# Backward-compatible import name used by the existing parser tests. The
# domain term in new code is VCCRequest, not a generic PaymentRequest.
PaymentRequest = VCCRequest
