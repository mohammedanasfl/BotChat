"""Exact fixed-window rate limiting backed by the RateLimiter Durable Object.

Cloudflare's Rate Limiting binding never blocks on live workers.dev (open Cloudflare issue,
workers-sdk#16097), so each limiter key gets its own Durable Object holding an exact counter.
"""

from __future__ import annotations

import json
from typing import Any

from core.context import RequestContext
from core.errors import ApiError, ErrorCode

PERIOD_SECONDS = 60
RETRY_AFTER_SECONDS = str(PERIOD_SECONDS)


def client_ip(ctx: RequestContext) -> str:
    # Set by Cloudflare's edge; absent only in local development. Used as a limiter key only.
    return ctx.headers.get("cf-connecting-ip", "local")


def count_hit(stored: str | None, now: float, period: int) -> tuple[str, int]:
    """Record one hit in the current fixed window. Returns (new stored state, hits in window)."""
    window = int(now // period)
    state = json.loads(stored) if stored else {}
    count = state.get("count", 0) + 1 if state.get("window") == window else 1
    return json.dumps({"window": window, "count": count}), count


async def enforce(namespace: Any, scope: str, key: str, limit: int) -> None:
    """Raise 429 when `scope:key` exceeds `limit` hits in the current window."""
    stub = namespace.getByName(f"{scope}:{key}")
    if not await stub.hit(limit, PERIOD_SECONDS):
        raise ApiError(ErrorCode.RATE_LIMITED, headers={"retry-after": RETRY_AFTER_SECONDS})
