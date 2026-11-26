"""Query embeddings via the Gemini REST API.

Request shape verified in Phase 2 (docs/rag.md): `taskType` and `outputDimensionality` must be
top-level fields; the nested `embedContentConfig` form is silently ignored (returns 3072 dims).
"""

from __future__ import annotations

from typing import Any

from config.embedding import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, QUERY_TASK_TYPE
from services.http import UpstreamError, request_json

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
EMBED_URL = f"{GEMINI_BASE}/models/{EMBEDDING_MODEL}:embedContent"


def build_request(text: str) -> dict[str, Any]:
    return {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {"parts": [{"text": text}]},
        "taskType": QUERY_TASK_TYPE,
        "outputDimensionality": EMBEDDING_DIMENSIONS,
    }


def parse_response(data: dict[str, Any]) -> list[float]:
    values = (data.get("embedding") or {}).get("values") or []
    if len(values) != EMBEDDING_DIMENSIONS:
        # A silent misconfiguration would otherwise produce wrong search results.
        raise UpstreamError(
            "gemini-embed", f"expected {EMBEDDING_DIMENSIONS} dims, got {len(values)}"
        )
    return [float(v) for v in values]


async def embed_query(text: str, api_key: str) -> list[float]:
    data = await request_json(
        "gemini-embed",
        EMBED_URL,
        method="POST",
        headers={"x-goog-api-key": api_key},
        body=build_request(text),
    )
    return parse_response(data)
