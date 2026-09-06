from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import PaymentOrder
from .payment_service import PaymentService


class ReconciliationService:
    """Facade for scheduled/manual reconciliation; uses PaymentService's one state path."""

    def __init__(self, payment_service: PaymentService):
        self.payment_service = payment_service

    def reconcile(self, *args, **kwargs):
        return self.payment_service.reconcile(*args, **kwargs)

    def scan_due(self, db: Session, *, trace_id_factory, limit: int = 20):
        now = datetime.now(timezone.utc)
        rows = (db.query(PaymentOrder)
                .filter(PaymentOrder.status == "PROCESSING", PaymentOrder.next_reconcile_at <= now)
                .order_by(PaymentOrder.next_reconcile_at.asc()).limit(min(limit, 20)).all())
        result = []
        for payment in rows:
            result.append(self.reconcile(db, payment_id=payment.id, actor_id="system", actor_role="system", trace_id=trace_id_factory()))
        return result
