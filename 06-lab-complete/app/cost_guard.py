"""
Cost guard (tiêu chí 8) — Theo dõi và chặn chi phí LLM theo ngày trong Redis.
"""
import time

from fastapi import HTTPException
import redis

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
COST_TTL_SECONDS = 2 * 24 * 3600

_fallback_daily_cost: dict[str, float] = {}


def _daily_key() -> str:
    return f"cost:daily:{time.strftime('%Y-%m-%d', time.gmtime())}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Vượt DAILY_BUDGET_USD → raise HTTPException(402)."""
    budget = settings.daily_budget_usd
    if budget <= 0:
        raise HTTPException(status_code=402, detail="Daily LLM budget exceeded.")

    key = _daily_key()
    if r is not None:
        try:
            spent = float(r.get(key) or 0.0)
            if spent >= budget:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "Daily budget exceeded",
                        "spent_usd": round(spent, 6),
                        "budget_usd": budget,
                    },
                )
            return
        except HTTPException:
            raise
        except redis.RedisError:
            pass

    spent = _fallback_daily_cost.get(key, 0.0)
    if spent >= budget:
        raise HTTPException(status_code=402, detail="Daily budget exceeded.")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí vào Redis và trả về chi phí lượt gọi."""
    cost = (
        (max(0, input_tokens) / 1000.0) * PRICE_INPUT_PER_1K
        + (max(0, output_tokens) / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    key = _daily_key()

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, COST_TTL_SECONDS)
            pipe.execute()
            return cost
        except redis.RedisError:
            pass

    _fallback_daily_cost[key] = _fallback_daily_cost.get(key, 0.0) + cost
    return cost
