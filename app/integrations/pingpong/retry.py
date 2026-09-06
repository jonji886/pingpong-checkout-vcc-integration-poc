from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

from .base import ProviderError

T = TypeVar("T")


class RetryPolicy:
    """Bounded exponential backoff with injectable sleep for deterministic tests."""

    def __init__(self, max_attempts: int = 3, base_delay: float = 0.25, jitter: Callable[[float], float] | None = None, sleep: Callable[[float], None] | None = None):
        self.max_attempts = max(1, max_attempts)
        self.base_delay = max(0.0, base_delay)
        self.jitter = jitter or (lambda value: random.uniform(0, value * 0.25))
        self.sleep = sleep or time.sleep

    def run(self, operation: Callable[[], T], *, retry_on_timeout: bool = False) -> T:
        attempt = 0
        while True:
            try:
                return operation()
            except ProviderError as exc:
                attempt += 1
                retryable = exc.retryable and (retry_on_timeout or exc.error_type != "timeout")
                if not retryable or attempt >= self.max_attempts:
                    raise
                delay = self.base_delay * (2 ** (attempt - 1)) + self.jitter(self.base_delay * (2 ** (attempt - 1)))
                self.sleep(delay)

    execute = run
