from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from .redaction import redact


def trace_id(value: str | None = None) -> str:
    return value or uuid.uuid4().hex


def safe_log(event: str, **fields: Any) -> None:
    """Structured, allowlisted logging helper (never accepts bodies or secrets)."""
    logging.getLogger("pingpong").info(json.dumps(redact({"event": event, **fields}), default=str, ensure_ascii=False))
