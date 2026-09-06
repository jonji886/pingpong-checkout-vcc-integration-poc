from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models import ApiIdempotency, AuditLog, ProviderCallLog


def new_id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def payload_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def hash_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def write_audit(db: Session, *, actor_id: Optional[str], actor_role: Optional[str], action: str, resource_type: str, resource_id: Optional[str], trace_id: str, outcome: str) -> None:
    db.add(AuditLog(id=new_id("audit"), actor_id=actor_id, actor_role=actor_role, action=action, resource_type=resource_type, resource_id=resource_id, trace_id=trace_id, outcome=outcome))


def write_provider_log(db: Session, *, provider: str, operation: str, trace_id: str, provider_request_id: Optional[str], http_status: Optional[int], provider_code: Optional[str], latency_ms: Optional[int], success: bool, error_type: Optional[str] = None) -> None:
    db.add(ProviderCallLog(id=new_id("pcall"), provider=provider, operation=operation, trace_id=trace_id, provider_request_id=provider_request_id, http_status=http_status, provider_code=provider_code, latency_ms=latency_ms, success=success, error_type=error_type))


def find_idempotency(db: Session, *, actor_id: str, method: str, route: str, key: str) -> Optional[ApiIdempotency]:
    return db.query(ApiIdempotency).filter_by(actor_id=actor_id, method=method, canonical_route=route, key_hash=hash_key(key)).first()

