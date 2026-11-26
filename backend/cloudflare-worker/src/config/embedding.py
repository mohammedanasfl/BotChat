"""Embedding configuration shared by the Worker (query embeddings) and the offline indexer
(document embeddings).

There is exactly ONE place to change these values, which guarantees that documents and queries
are embedded identically. Changing the model or dimensions requires recreating the Vectorize
index (its dimensions are fixed at creation) and a full reindex.
"""

from __future__ import annotations

EMBEDDING_MODEL = "gemini-embedding-001"

# Gemini supports 128-3072 (recommended 768/1536/3072). Cloudflare Vectorize allows at most 1536.
EMBEDDING_DIMENSIONS = 768
VECTORIZE_MAX_DIMENSIONS = 1536

DOCUMENT_TASK_TYPE = "RETRIEVAL_DOCUMENT"
QUERY_TASK_TYPE = "RETRIEVAL_QUERY"

# Similarity metric the Vectorize index is created with. Cosine makes scores independent of
# vector length, so truncated (non-3072) Gemini embeddings need no client-side normalization.
VECTORIZE_METRIC = "cosine"


def validate_embedding_config() -> None:
    if not 128 <= EMBEDDING_DIMENSIONS <= VECTORIZE_MAX_DIMENSIONS:
        raise ValueError(
            f"EMBEDDING_DIMENSIONS={EMBEDDING_DIMENSIONS} must be within "
            f"128..{VECTORIZE_MAX_DIMENSIONS}"
        )
