"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import redis

from app.config import settings

# Lazy connection pool: không ping Redis lúc import để app vẫn khởi động được khi chưa có Redis
r: redis.Redis | None = (
    redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1.5,
        socket_timeout=1.5,
    )
    if settings.redis_url
    else None
)


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis thực tế cho endpoint GET /ready."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False
