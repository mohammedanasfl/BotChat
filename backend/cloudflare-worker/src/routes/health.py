"""Health endpoints.

GET /api/health        liveness: the Worker is running (no dependency calls).
GET /api/health/ready  readiness: the knowledge index and Gemini are usable. Returns only
                       ready/not_ready; the reason goes to logs, never to the client.
"""

from __future__ import annotations

from config.embedding import EMBEDDING_MODEL
from config.settings import require_gemini_key
from core.context import RequestContext
from core.log import log_event
from core.responses import JsonResult, json_result
from services.embeddings import GEMINI_BASE
from services.http import request_json
from services.retrieval import describe, index_status


def health(ctx: RequestContext) -> JsonResult:
    return json_result({"status": "ok", "version": ctx.settings.version})


async def ready(ctx: RequestContext) -> JsonResult:
    try:
        ok, reason = index_status(await describe(ctx.env.VECTORIZE))
        if ok:
            # Model lookups confirm the key works and both models exist; they use no tokens.
            key = require_gemini_key(ctx.settings)
            for model in (EMBEDDING_MODEL, ctx.settings.gemini_model):
                await request_json(
                    "gemini-models",
                    f"{GEMINI_BASE}/models/{model}",
                    headers={"x-goog-api-key": key},
                )
    except Exception as error:
        ok, reason = False, f"{type(error).__name__}: {error}"

    if not ok:
        log_event("warning", "not_ready", request_id=ctx.request_id, reason=reason)
        return json_result({"status": "not_ready"}, status=503)
    return json_result({"status": "ready"})
