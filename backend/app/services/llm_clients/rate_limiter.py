"""Rate limiting and retry logic for LLM API calls with exponential backoff."""
import asyncio
import random
from functools import wraps
from typing import Callable, TypeVar

from ...utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


def with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True
):
    """
    Decorator for async functions that implements exponential backoff retry logic.

    This protects against transient API failures and rate limiting by automatically
    retrying with increasing delays between attempts.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 60.0)
        jitter: Add randomization to delay to prevent thundering herd (default: True)

    Returns:
        Decorated async function with retry logic

    Example:
        @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
        async def upload_file(self, file_path: str) -> str:
            # API call that might fail with rate limiting
            return await self.client.upload(file_path)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_str = str(e).lower()

                    # Check if error is retryable
                    is_rate_limit = any(
                        pattern in error_str
                        for pattern in ['rate_limit', '429', 'too many requests', 'quota']
                    )
                    is_timeout = any(
                        pattern in error_str
                        for pattern in ['timeout', 'timed out', 'deadline']
                    )
                    is_server_error = any(
                        pattern in error_str
                        for pattern in ['500', '502', '503', '504', 'server error']
                    )

                    is_retryable = is_rate_limit or is_timeout or is_server_error

                    if not is_retryable or attempt == max_retries:
                        if not is_retryable:
                            logger.error(
                                "Non-retryable error for %s: %s",
                                func.__name__, e
                            )
                        else:
                            logger.error(
                                "Max retries reached for %s: %s",
                                func.__name__, e
                            )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if jitter:
                        # Add jitter: delay * random(0.5, 1.5)
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        func.__name__,
                        attempt + 1,
                        max_retries + 1,
                        e,
                        delay
                    )
                    await asyncio.sleep(delay)

            # This should never be reached, but just in case
            raise last_exception

        return wrapper
    return decorator
