from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            payload["trace_id"] = trace_id
        for field in ("latency_ms", "method", "path", "status_code"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging() -> None:
    logger = logging.getLogger("app.request")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class RequestTraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        request.state.trace_id = trace_id
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        logging.getLogger("app.request").info(
            "request completed",
            extra={
                "trace_id": trace_id,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response
