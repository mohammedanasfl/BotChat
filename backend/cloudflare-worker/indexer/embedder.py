"""Gemini document embeddings: batched, with a few retries on rate limits."""

from __future__ import annotations

import time

from config.embedding import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

BATCH_SIZE = 50
RETRYABLE = {429, 500, 503}


def embed_texts(client, texts: list[str], task_type: str, attempts: int = 3) -> list[list[float]]:
    """Embed texts with the google-genai `client`, BATCH_SIZE per request.

    Every vector is checked to have exactly EMBEDDING_DIMENSIONS values: a mismatch means the
    request was misconfigured and the vectors would not fit the Vectorize index.
    """
    from google.genai import types

    config = types.EmbedContentConfig(
        task_type=task_type, output_dimensionality=EMBEDDING_DIMENSIONS
    )
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        for attempt in range(1, attempts + 1):
            try:
                response = client.models.embed_content(
                    model=EMBEDDING_MODEL, contents=batch, config=config
                )
                break
            except Exception as error:
                if getattr(error, "code", None) not in RETRYABLE or attempt == attempts:
                    raise
                time.sleep(2**attempt)  # 2 s, 4 s
        batch_vectors = [list(e.values) for e in response.embeddings]
        if len(batch_vectors) != len(batch) or any(
            len(v) != EMBEDDING_DIMENSIONS for v in batch_vectors
        ):
            raise ValueError(f"Expected {len(batch)} vectors of {EMBEDDING_DIMENSIONS} dims")
        vectors.extend(batch_vectors)
    return vectors
