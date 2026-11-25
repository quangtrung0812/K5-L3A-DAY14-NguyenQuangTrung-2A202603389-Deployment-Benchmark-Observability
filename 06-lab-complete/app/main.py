"""
Production AI Agent — Part 6 Final Project
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import sys
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mỗi bản ghi log thành 1 JSON object hợp lệ trên 1 dòng."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_data = getattr(record, "structured", None)
        if isinstance(extra_data, dict):
            payload.update(extra_data)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logger() -> logging.Logger:
    app_logger = logging.getLogger("agent")
    app_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger.addHandler(handler)
    app_logger.propagate = False
    return app_logger


logger = _setup_logger()
START_TIME = time.time()
_shutting_down = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý khởi động và graceful shutdown khi nhận SIGTERM từ container/uvicorn."""
    global _shutting_down
    _shutting_down = False
    logger.info(
        "agent_startup",
        extra={
            "structured": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
                "rate_limit_per_minute": settings.rate_limit_per_minute,
                "daily_budget_usd": settings.daily_budget_usd,
            }
        },
    )
    yield
    _shutting_down = True
    logger.info(
        "agent_shutdown",
        extra={"structured": {"event": "shutdown", "reason": "SIGTERM_or_lifespan_exit"}},
    )
    if r is not None:
        try:
            r.close()
        except Exception:
            pass


app = FastAPI(
    title="Production AI Agent",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.environment == "production" else "/docs",
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    logger.info(
        "http_request",
        extra={
            "structured": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Không để lộ stack trace nội bộ ra phía client."""
    logger.error(
        "unhandled_error",
        extra={
            "structured": {
                "event": "error",
                "path": request.url.path,
                "error_type": type(exc).__name__,
            }
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi tiến trình còn sống (không phụ thuộc Redis)."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "environment": settings.environment,
    }


@app.get("/ready")
def ready():
    """Readiness probe: trả 200 khi sẵn sàng, 503 khi đang tắt hoặc mất kết nối Redis."""
    if _shutting_down or not redis_healthy():
        raise HTTPException(status_code=503, detail="Service not ready: Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
async def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    """Protected endpoint: Auth (401) → Rate Limit (429) → Cost Guard (402) → LLM (200)."""
    check_rate_limit(api_key)
    check_budget()

    answer = await asyncio.to_thread(llm_ask, body.question)

    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost_usd = record_cost(input_tokens, output_tokens)

    logger.info(
        "ask_completed",
        extra={
            "structured": {
                "event": "ask",
                "question_chars": len(body.question),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost_usd, 6),
            }
        },
    )
    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": round(cost_usd, 6),
    }
