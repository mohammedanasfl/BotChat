"""POST /api/dev/answer: development-only RAG check (404 in production).

Runs the full pipeline (embed -> Vectorize -> Gemini) and returns the answer plus the retrieved
chunks and scores for debugging. The public, authenticated, streaming POST /api/chat replaces it
in Phase 8.
"""

from __future__ import annotations

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


async def dev_answer(ctx: RequestContext) -> JsonResult:
    if ctx.settings.is_production:
        raise ApiError(ErrorCode.NOT_FOUND)
    message, history = _parse(ctx)
    result = await rag.answer(message, history, ctx.settings, ctx.env.VECTORIZE)
    return json_result(
        {
            "answer": result.text,
            "finish_reason": result.finish_reason,
            "sources": [
                {"chunk_id": c.chunk_id, "heading": c.heading, "score": round(c.score, 4)}
                for c in result.sources
            ],
            "usage": result.usage,
        }
    )
