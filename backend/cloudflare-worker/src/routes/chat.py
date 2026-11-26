"""POST /api/chat: authenticated, rate-limited RAG answer.

Returns JSON for now; Phase 8 switches the response to Server-Sent Events.
"""

from __future__ import annotations

import time

from core.auth import require_session
from core.context import RequestContext
from core.log import log_event
from core.rate_limit import client_ip, enforce
from core.responses import JsonResult, json_result
from core.validation import parse_chat_request
from services import rag


async def chat(ctx: RequestContext) -> JsonResult:
    started = time.monotonic()
    # Cheapest checks first: the IP limit also blunts floods of invalid tokens.
    limiter, limits = ctx.env.RATE_LIMITER, ctx.settings
    await enforce(limiter, "chat-ip", client_ip(ctx), limits.rate_chat_ip)
    session = require_session(ctx)
    await enforce(limiter, "chat-session", session["sub"], limits.rate_chat_session)
    request = parse_chat_request(ctx.json(), ctx.settings)

    result = await rag.answer(request.message, request.history, ctx.settings, ctx.env.VECTORIZE)

    log_event(
        "info",
        "chat_completed",
        request_id=ctx.request_id,
        session=session["sub"],
        conversation_id=request.conversation_id,
        prompt_tokens=result.usage.get("promptTokenCount"),
        output_tokens=result.usage.get("candidatesTokenCount"),
        sources=len(result.sources),
        finish_reason=result.finish_reason,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    return json_result(
        {
            "answer": result.text,
            "finish_reason": result.finish_reason,
            "sources": [{"chunk_id": c.chunk_id, "heading": c.heading} for c in result.sources],
        }
    )
