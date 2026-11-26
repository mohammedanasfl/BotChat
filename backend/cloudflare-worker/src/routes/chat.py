"""POST /api/chat: authenticated RAG answer.

Requires a session token from POST /api/session. Returns JSON for now; Phase 7 adds rate limits
and full request validation, Phase 8 switches the response to Server-Sent Events.
"""

from __future__ import annotations

from core.auth import require_session
from core.context import RequestContext
from core.errors import ApiError, ErrorCode
from core.responses import JsonResult, json_result
from prompts.builder import Turn
from services import rag


def _parse(ctx: RequestContext) -> tuple[str, list[Turn]]:
    data = ctx.json()
    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ApiError(ErrorCode.VALIDATION_ERROR, "'message' must be a non-empty string.")
    if len(message) > ctx.settings.max_message_chars:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "'message' is too long.")
    history = []
    for item in data.get("history") or []:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            raise ApiError(ErrorCode.VALIDATION_ERROR, "Invalid 'history' item.")
        history.append(Turn(item["role"], str(item.get("content", ""))))
    return message.strip(), history


async def chat(ctx: RequestContext) -> JsonResult:
    require_session(ctx)
    message, history = _parse(ctx)
    result = await rag.answer(message, history, ctx.settings, ctx.env.VECTORIZE)
    return json_result(
        {
            "answer": result.text,
            "finish_reason": result.finish_reason,
            "sources": [{"chunk_id": c.chunk_id, "heading": c.heading} for c in result.sources],
        }
    )
