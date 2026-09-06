from __future__ import annotations

from sqlalchemy.orm import Session

from ..domain.vcc import transition_vcc
from ..integrations.pingpong.base import IssuingProvider
from ..models import VCCApplication
from .common import write_audit


class IssuingService:
    def __init__(self, provider: IssuingProvider): self.provider = provider

    def create_vcc(self, db: Session, *, application_id: str, actor_id: str, actor_role: str, trace_id: str, human_confirmed: bool = False) -> VCCApplication:
        if actor_role not in {"finance", "admin"}:
            raise PermissionError("finance role required")
        if not human_confirmed:
            raise PermissionError("human confirmation required")
        app = db.get(VCCApplication, application_id)
        if not app: raise ValueError("application not found")
        if app.status != "APPROVED" or app.approval_status not in {"APPROVED", "AUTO_APPROVED"}: raise PermissionError("human approval required")
        if app.provider_card_id: return app
        write_audit(db, actor_id=actor_id, actor_role=actor_role, action="CONFIRM_VCC_ISSUANCE", resource_type="VCCApplication", resource_id=app.id, trace_id=trace_id, outcome="CONFIRMED")
        app.status = transition_vcc(app.status, "CARD_CREATING")
        result = self.provider.create_vcc(application_id=app.id, vendor=app.vendor, amount=app.amount, currency=app.currency, period_days=app.period)
        app.provider_card_id = result["provider_card_id"]
        app.masked_card = result.get("masked_card") or None
        provider_status = str(result.get("status") or "ACTIVE").upper()
        if provider_status == "ACTIVE":
            app.status = transition_vcc(app.status, "ACTIVE")
        write_audit(db, actor_id=actor_id, actor_role=actor_role, action="CREATE_VCC", resource_type="VCCApplication", resource_id=app.id, trace_id=trace_id, outcome=app.status)
        db.commit()
        return app
