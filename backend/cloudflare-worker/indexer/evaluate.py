"""Retrieval evaluation: does each realistic question retrieve the right section?

Scores are cosine similarity, exactly what Vectorize computes (metric=cosine; with ~35 vectors
its search is exact), so this runs locally against the embedding cache.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from indexer.chunker import Chunk


@dataclass(frozen=True)
class Result:
    question: str
    expected: list[str]  # acceptable heading paths; empty = off-topic (should match nothing)
    ranked: list[tuple[float, Chunk]]  # top matches, best first

    @property
    def top_score(self) -> float:
        return self.ranked[0][0]

    @property
    def rank(self) -> int | None:
        """1-based rank of the first acceptable chunk, or None."""
        for i, (_, chunk) in enumerate(self.ranked, start=1):
            if chunk.heading_path in self.expected:
                return i
        return None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def rank_chunks(
    query: list[float], chunks: list[Chunk], vectors: dict[str, list[float]], top_k: int = 4
) -> list[tuple[float, Chunk]]:
    scored = [(cosine(query, vectors[c.content_sha256]), c) for c in chunks]
    return sorted(scored, key=lambda pair: pair[0], reverse=True)[:top_k]


def summarize(results: list[Result]) -> dict[str, float]:
    answerable = [r for r in results if r.expected]
    off_topic = [r for r in results if not r.expected]
    correct_scores = [r.ranked[r.rank - 1][0] for r in answerable if r.rank]
    return {
        "hit_at_1": sum(r.rank == 1 for r in answerable) / len(answerable),
        "hit_at_3": sum(r.rank is not None and r.rank <= 3 for r in answerable) / len(answerable),
        "min_correct_score": min(correct_scores, default=0.0),
        "max_off_topic_score": max((r.top_score for r in off_topic), default=0.0),
    }
