#!/usr/bin/env python3
"""One bounded reconciliation pass; schedule externally (cron/worker) for SQLite."""
import uuid

from app.db import SessionLocal, init_db
from app.integrations.pingpong.factory import checkout_provider
from app.config import settings
from app.services.payment_service import PaymentService
from app.services.reconciliation_service import ReconciliationService

init_db()
db = SessionLocal()
try:
    rows = ReconciliationService(PaymentService(checkout_provider(settings.pingpong_mode))).scan_due(db, trace_id_factory=lambda: uuid.uuid4().hex, limit=20)
    print("reconciled", len(rows))
finally:
    db.close()

