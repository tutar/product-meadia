import asyncio
from functools import wraps


def retry_async(max_attempts: int = 3, base_delay: float = 1.0):
    """Decorator: retry an async function with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt == max_attempts - 1:
                        raise
                    await asyncio.sleep(base_delay * (2 ** attempt))
            raise last_error
        return wrapper
    return decorator
