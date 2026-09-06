from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from ..domain.vcc import approval_required, budget_check, transition_vcc
from ..models import VCCApplication
from .common import new_id, write_audit


class ApprovalService:
    @staticmethod
    def evaluate_budget(amount: Decimal) -> bool:
        return budget_check(amount)

    @staticmethod
    def create_application(db: Session, *, requester_id: str, vendor: str, purpose: str, amount: Decimal, currency: str, period_days: int, trace_id: str) -> VCCApplication:
        if currency.upper() != "USD" or amount <= 0 or period_days <= 0:
            raise ValueError("invalid VCC request")
        requires_human = approval_required(amount)
        initial_status = transition_vcc("DRAFT", "PENDING_APPROVAL") if requires_human else "APPROVED"
        app = VCCApplication(id=new_id("vcc"), requester_id=requester_id, vendor=vendor, purpose=purpose, amount=amount, currency="USD", period=period_days, status=initial_status, approval_status="PENDING" if requires_human else "AUTO_APPROVED")
        db.add(app)
        write_audit(db, actor_id=requester_id, actor_role="finance", action="CREATE_VCC_APPLICATION", resource_type="VCCApplication", resource_id=app.id, trace_id=trace_id, outcome=app.status)
        db.commit()
        return app

    @staticmethod
    def approve(db: Session, *, application_id: str, approver_id: str, approve: bool, trace_id: str) -> VCCApplication:
        app = db.get(VCCApplication, application_id)
        if not app: raise ValueError("application not found")
        if app.status != "PENDING_APPROVAL": raise ValueError("application is not pending approval")
        if approve:
            app.status = transition_vcc(app.status, "APPROVED"); app.approval_status = "APPROVED"
            outcome = "APPROVED"
        else:
            app.status = transition_vcc(app.status, "REJECTED"); app.approval_status = "REJECTED"
            outcome = "REJECTED"
        write_audit(db, actor_id=approver_id, actor_role="approver", action="APPROVE_VCC", resource_type="VCCApplication", resource_id=application_id, trace_id=trace_id, outcome=outcome)
        db.commit()
        return app
