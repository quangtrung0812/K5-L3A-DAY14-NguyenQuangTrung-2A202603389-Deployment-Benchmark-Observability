"""
Rate limiting (tiêu chí 7) — Sliding window 60 giây lưu trong Redis Sorted Set.
"""
from collections import defaultdict, deque
import hashlib
import time
import uuid

from fastapi import HTTPException
import redis

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60
_fallback_windows: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    """Giới hạn tối đa RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    limit = settings.rate_limit_per_minute
    now = time.time()
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    redis_key = f"ratelimit:{key_hash}"

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
            pipe.zcard(redis_key)
            _, current_count = pipe.execute()

            if current_count >= limit:
                oldest = r.zrange(redis_key, 0, 0, withscores=True)
                retry_after = (
                    max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
                    if oldest
                    else WINDOW_SECONDS
                )
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please retry later.",
                    headers={"Retry-After": str(retry_after)},
                )

            member = f"{now}:{uuid.uuid4().hex[:8]}"
            write_pipe = r.pipeline()
            write_pipe.zadd(redis_key, {member: now})
            write_pipe.expire(redis_key, WINDOW_SECONDS + 5)
            write_pipe.execute()
            return
        except HTTPException:
            raise
        except redis.RedisError:
            pass

    # Fallback khi chạy local đơn lẻ chưa bật Redis
    window = _fallback_windows[key_hash]
    while window and window[0] <= now - WINDOW_SECONDS:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please retry later.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
    window.append(now)
