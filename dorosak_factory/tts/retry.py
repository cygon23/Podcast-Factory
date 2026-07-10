"""Exponential-backoff retry helper shared by every cloud TTS adapter.

Each adapter owns its own retryable-exception set (rate limits, transient
5xx errors) per INSTRUCTIONS.md 4.1 ("own its provider's chunking limits,
retries with exponential backoff, and rate limiting").
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def with_retries(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    retryable_exceptions: Sequence[type[Exception]] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Calls `fn()`, retrying on `retryable_exceptions` with exponential backoff.

    Delay before attempt N (1-indexed, N>1) is `base_delay_seconds * 2**(N-2)`.
    Re-raises the last exception once `max_attempts` is exhausted.
    """
    last_exception: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except tuple(retryable_exceptions) as exc:
            last_exception = exc
            if attempt == max_attempts:
                raise
            sleep(base_delay_seconds * (2 ** (attempt - 1)))
    raise last_exception  # pragma: no cover - unreachable, satisfies type checkers
