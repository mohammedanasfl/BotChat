"""Retrieval-augmented answer: search the knowledge index, then generate a grounded answer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.settings import Settings, require_gemini_key
from prompts.builder import Turn, build_generate_request, retrieval_query
from services import embeddings, gemini_client, retrieval


@dataclass(frozen=True)
class Answer:
    text: str
    finish_reason: str
    sources: list[retrieval.RetrievedChunk]
    usage: dict[str, int]


async def answer(message: str, history: list[Turn], settings: Settings, index: Any) -> Answer:
    api_key = require_gemini_key(settings)
    vector = await embeddings.embed_query(retrieval_query(message, history), api_key)
    chunks = await retrieval.search(index, vector, settings.search_top_k, settings.search_min_score)
    request = build_generate_request(
        message,
        history,
        chunks,
        max_history=settings.max_history_messages,
        max_output_tokens=settings.gemini_max_output_tokens,
    )
    generation = await gemini_client.generate(request, model=settings.gemini_model, api_key=api_key)
    return Answer(generation.text, generation.finish_reason, chunks, generation.usage)
