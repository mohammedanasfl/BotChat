"""Live Gemini check (skipped without a key): uv run --env-file .env pytest tests/live"""

import math
import os

import pytest

from config.embedding import DOCUMENT_TASK_TYPE, QUERY_TASK_TYPE
from indexer.embedder import embed_texts

pytestmark = pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="no GEMINI_API_KEY")


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True)) / (math.hypot(*a) * math.hypot(*b))


def test_related_text_scores_higher_than_unrelated():
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    polo, hours = embed_texts(
        client,
        [
            "Products › Classic Polo T-Shirt\n\nFabric: 100% cotton pique.",
            "Company › Working hours\n\nMonday to Saturday, 9 AM to 7 PM IST.",
        ],
        DOCUMENT_TASK_TYPE,
    )
    (query,) = embed_texts(client, ["What fabric are your polo shirts?"], QUERY_TASK_TYPE)
    assert cosine(query, polo) > cosine(query, hours)
