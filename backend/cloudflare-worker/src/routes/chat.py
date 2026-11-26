"""POST /api/chat: authenticated, rate-limited, streaming RAG answer (Server-Sent Events).

Before the stream starts (normal JSON errors): rate limits, session, validation, retrieval and
opening the Gemini stream. After it starts, failures arrive as an SSE `error` event.

Events: start -> token* -> complete (with follow_ups) | error   (see docs/api-contract.md)
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from config.settings import require_gemini_key
from core.auth import require_session
from core.context import RequestContext
from core.log import log_event
from core.rate_limit import client_ip, enforce
from core.sse import StreamResult, format_event
from core.validation import ChatRequest, parse_chat_request
from services import gemini_stream, rag
from services.follow_ups import FollowUpSplitter
from services.retrieval import RetrievedChunk

STREAM_ERROR = {
    "code": "upstream_unavailable",
    "message": "The assistant is temporarily unavailable. Please try again.",
}


async def chat(ctx: RequestContext) -> StreamResult:
    started = time.monotonic()
    limiter, settings = ctx.env.RATE_LIMITER, ctx.settings
    # Cheapest checks first: the IP limit also blunts floods of invalid tokens.
    await enforce(limiter, "chat-ip", client_ip(ctx), settings.rate_chat_ip)
    session = require_session(ctx)
    await enforce(limiter, "chat-session", session["sub"], settings.rate_chat_session)
    request = parse_chat_request(ctx.json(), settings)

    gemini_request, sources = await rag.prepare(
        request.message, request.history, settings, ctx.env.VECTORIZE
    )
    response = await gemini_stream.open_stream(
        gemini_request,
        model=settings.gemini_model,
        api_key=require_gemini_key(settings),
        abort_signal=ctx.abort_signal,
    )
    return StreamResult(events=_events(ctx, request, session, sources, response, started))


async def _events(
    ctx: RequestContext,
    request: ChatRequest,
    session: dict[str, Any],
    sources: list[RetrievedChunk],
    response: Any,
    started: float,
) -> AsyncIterator[str]:
    yield format_event(
        "start", {"request_id": ctx.request_id, "conversation_id": request.conversation_id}
    )
    state = gemini_stream.StreamState()
    splitter = FollowUpSplitter()
    answered = False
    try:
        async for text in gemini_stream.iter_deltas(response, state):
            if visible := splitter.feed(text):
                answered = True
                yield format_event("token", {"text": visible})
    except Exception as error:
        if getattr(ctx.abort_signal, "aborted", False):
            # The visitor closed the connection; Gemini was aborted via the same signal.
            log_event("info", "client_disconnected", request_id=ctx.request_id)
            return
        log_event("error", "stream_failed", request_id=ctx.request_id, error=type(error).__name__)
        yield format_event("error", STREAM_ERROR)
        return
    rest, follow_ups = splitter.finish()
    if rest:
        answered = True
        yield format_event("token", {"text": rest})
    if not answered:
        log_event("error", "stream_empty", request_id=ctx.request_id, finish=state.finish_reason)
        yield format_event("error", STREAM_ERROR)
        return

    yield format_event(
        "complete",
        {
            "finish_reason": state.finish_reason,
            "follow_ups": follow_ups,
            "sources": [{"chunk_id": c.chunk_id, "heading": c.heading} for c in sources],
        },
    )
    log_event(
        "info",
        "chat_completed",
        request_id=ctx.request_id,
        session=session["sub"],
        conversation_id=request.conversation_id,
        prompt_tokens=state.usage.get("promptTokenCount"),
        output_tokens=state.usage.get("candidatesTokenCount"),
        sources=len(sources),
        finish_reason=state.finish_reason,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
