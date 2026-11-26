"""Knowledge retrieval from the Vectorize index (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.embedding import EMBEDDING_DIMENSIONS
from core.interop import to_js, to_python


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    heading: str
    text: str
    score: float


def filter_matches(matches: list[dict[str, Any]], min_score: float) -> list[RetrievedChunk]:
    chunks = []
    for match in matches:
        metadata = match.get("metadata") or {}
        if match.get("score", 0.0) < min_score or not metadata.get("text"):
            continue
        chunks.append(
            RetrievedChunk(
                chunk_id=str(match["id"]),
                heading=str(metadata.get("heading", "")),
                text=str(metadata["text"]),
                score=float(match["score"]),
            )
        )
    return chunks


async def search(
    index: Any, vector: list[float], top_k: int, min_score: float
) -> list[RetrievedChunk]:
    result = to_python(
        await index.query(to_js(vector), to_js({"topK": top_k, "returnMetadata": "all"}))
    )
    return filter_matches(result.get("matches", []), min_score)


def index_status(info: dict[str, Any]) -> tuple[bool, str]:
    """(ready, reason) from VECTORIZE.describe(); tolerates V1/V2 field names."""
    dims = info.get("dimensions") or (info.get("config") or {}).get("dimensions")
    count = info.get("vectorCount", info.get("vectorsCount", 0))
    if dims != EMBEDDING_DIMENSIONS:
        return False, f"index dimensions {dims} != {EMBEDDING_DIMENSIONS}"
    if not count:
        return False, "index is empty"
    return True, "ok"


async def describe(index: Any) -> dict[str, Any]:
    return to_python(await index.describe())
