import asyncio
import time
from collections import defaultdict

from app.core.config import settings
from app.core.exceptions import RateLimitError

_memory_limits: dict[str, list[float]] = defaultdict(list)
_memory_lock = asyncio.Lock()


async def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    namespaced_key = f"rate-limit:{key}"
    if not settings.DEBUG:
        try:
            from redis.asyncio import from_url

            redis = from_url(settings.REDIS_URL, decode_responses=True)
            try:
                count = await redis.incr(namespaced_key)
                if count == 1:
                    await redis.expire(namespaced_key, window_seconds)
                if count > limit:
                    raise RateLimitError()
                return
            finally:
                await redis.aclose()
        except RateLimitError:
            raise
        except Exception:
            pass

    now = time.monotonic()
    cutoff = now - window_seconds
    async with _memory_lock:
        attempts = [timestamp for timestamp in _memory_limits[namespaced_key] if timestamp > cutoff]
        if len(attempts) >= limit:
            raise RateLimitError()
        attempts.append(now)
        _memory_limits[namespaced_key] = attempts
