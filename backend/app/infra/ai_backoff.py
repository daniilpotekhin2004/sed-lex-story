from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryableAIError(Exception):
    """Represents a transient AI error that can be retried."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NonRetryableAIError(Exception):
    """Represents a permanent AI error that should not be retried."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def run_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 0.6,
    max_delay: float = 8.0,
    jitter_ratio: float = 0.2,
    retry_on: Tuple[Type[BaseException], ...] = (RetryableAIError,),
) -> T:
    """Run an async callable with exponential backoff.

    Args:
        fn: Async callable to invoke.
        retries: Max retry attempts (not counting the first try).
        base_delay: Initial delay in seconds.
        max_delay: Max delay between retries.
        jitter_ratio: Random jitter ratio applied to the delay.
        retry_on: Exception types that should trigger a retry.
    """
    attempt = 0
    while True:
        try:
            return await fn()
        except retry_on as exc:
            if attempt >= retries:
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            jitter = random.uniform(0, delay * jitter_ratio)
            sleep_for = delay + jitter
            logger.warning(
                "AI call failed (%s). Retrying in %.2fs (%s/%s)",
                exc,
                sleep_for,
                attempt + 1,
                retries,
            )
            await asyncio.sleep(sleep_for)
            attempt += 1

