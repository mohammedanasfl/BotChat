"""POST /api/dev/search: development-only retrieval check (404 in production).

Exercises the real path the chat endpoint will use: embed the question with Gemini, query
Vectorize, filter by SEARCH_MIN_SCORE. Replaced by POST /api/chat in Phase 5.
"""

from __future__ import annotations

from config.settings import require_gemini_key
from core.context import RequestContext
from core.errors import ApiError, ErrorCode
from core.responses import JsonResult, json_result
from services.embeddings import embed_query
from services.http import UpstreamError
from services.retrieval import search


async def dev_search(ctx: RequestContext) -> JsonResult:
    if ctx.settings.is_production:
        raise ApiError(ErrorCode.NOT_FOUND)

    query = ctx.json().get("query")
    if not isinstance(query, str) or not query.strip():
        raise ApiError(ErrorCode.VALIDATION_ERROR, "'query' must be a non-empty string.")
    if len(query) > ctx.settings.max_message_chars:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "'query' is too long.")

    try:
        vector = await embed_query(query.strip(), require_gemini_key(ctx.settings))
        chunks = await search(
            ctx.env.VECTORIZE, vector, ctx.settings.search_top_k, ctx.settings.search_min_score
        )
    except UpstreamError as error:
        raise ApiError(ErrorCode.UPSTREAM_UNAVAILABLE) from error

    return json_result(
        {
            "query": query,
            "results": [
                {
                    "chunk_id": c.chunk_id,
                    "heading": c.heading,
                    "score": round(c.score, 4),
                    "text": c.text,
                }
                for c in chunks
            ],
        }
    )
