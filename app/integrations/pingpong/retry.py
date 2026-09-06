from __future__ import annotations

import random
import time
import logging
from typing import Callable, Optional, Protocol, TypeVar

from .base import ProviderError

T = TypeVar("T")
logger = logging.getLogger(__name__)


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class RealSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class NoOpSleeper:
    def sleep(self, seconds: float) -> None:
        return None


class RetryPolicy:
    """Bounded exponential backoff with injectable sleep for deterministic tests."""

    def __init__(self, max_attempts: int = 3, base_delay: float = 0.25, max_delay: float = 5.0, jitter: Callable[[float], float] | None = None, sleeper: Optional[Sleeper] = None, sleep: Callable[[float], None] | None = None, on_retry: Optional[Callable[[int, ProviderError, float], None]] = None):
        self.max_attempts = max(1, max_attempts)
        self.base_delay = max(0.0, base_delay)
        self.max_delay = max(0.0, max_delay)
        self.jitter = jitter or (lambda value: random.uniform(0, value * 0.25))
        self.sleeper = sleeper or (type("CallableSleeper", (), {"sleep": staticmethod(sleep)})() if sleep else RealSleeper())
        self.on_retry = on_retry

    def run(self, operation: Callable[[], T], *, retry_on_timeout: bool = False, operation_name: str = "provider_call", request_id: str = "") -> T:
        attempt = 0
        while True:
            try:
                return operation()
            except ProviderError as exc:
                attempt += 1
                retryable = exc.retryable and (retry_on_timeout or exc.error_type != "timeout")
                if not retryable or attempt >= self.max_attempts:
                    raise
                exponential = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
                retry_after = getattr(exc, "retry_after", None)
                delay = min(self.max_delay, max(float(retry_after or 0), exponential + self.jitter(exponential)))
                if self.on_retry:
                    self.on_retry(attempt, exc, delay)
                logger.info("provider_retry", extra={"operation": operation_name, "request_id": request_id, "attempt": attempt, "error_type": exc.error_type, "delay_seconds": delay})
                self.sleeper.sleep(delay)

    execute = run
