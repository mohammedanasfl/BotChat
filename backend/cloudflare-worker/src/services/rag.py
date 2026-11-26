"""Retrieval-augmented generation: retrieve knowledge, then build the grounded Gemini request."""

from __future__ import annotations

from typing import Any

from config.settings import Settings, require_gemini_key
from prompts.builder import Turn, build_generate_request, retrieval_query
from services import embeddings, retrieval


async def prepare(
    message: str, history: list[Turn], settings: Settings, index: Any
) -> tuple[dict[str, Any], list[retrieval.RetrievedChunk]]:
    """Embed the search query, retrieve chunks, and return (Gemini request, sources)."""
    vector = await embeddings.embed_query(
        retrieval_query(message, history), require_gemini_key(settings)
    )
    chunks = await retrieval.search(index, vector, settings.search_top_k, settings.search_min_score)
    request = build_generate_request(
        message,
        history,
        chunks,
        max_history=settings.max_history_messages,
        max_output_tokens=settings.gemini_max_output_tokens,
    )
    return request, chunks
