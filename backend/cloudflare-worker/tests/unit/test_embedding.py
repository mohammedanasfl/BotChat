from types import SimpleNamespace

import pytest

from config.embedding import DOCUMENT_TASK_TYPE, EMBEDDING_DIMENSIONS
from indexer import embedder
from indexer.cache import load_cache, save_cache
from indexer.embedder import embed_texts


class FakeClient:
    """Mimics `genai.Client().models.embed_content`."""

    def __init__(self, dims=EMBEDDING_DIMENSIONS, failures=()):
        self.batches, self.failures, self.dims = [], list(failures), dims
        self.models = self

    def embed_content(self, *, model, contents, config):
        if self.failures:
            raise self.failures.pop(0)
        self.batches.append(len(contents))
        vectors = [SimpleNamespace(values=[float(len(t))] * self.dims) for t in contents]
        return SimpleNamespace(embeddings=vectors)


class RateLimited(Exception):
    code = 429


def test_batches_and_preserves_order(monkeypatch):
    monkeypatch.setattr(embedder, "BATCH_SIZE", 2)
    client = FakeClient()
    vectors = embed_texts(client, ["a", "bb", "ccc"], DOCUMENT_TASK_TYPE)
    assert client.batches == [2, 1]
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0]


def test_retries_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr(embedder.time, "sleep", lambda _s: None)
    client = FakeClient(failures=[RateLimited()])
    assert len(embed_texts(client, ["a"], DOCUMENT_TASK_TYPE)) == 1


def test_gives_up_after_attempts(monkeypatch):
    monkeypatch.setattr(embedder.time, "sleep", lambda _s: None)
    with pytest.raises(RateLimited):
        embed_texts(FakeClient(failures=[RateLimited()] * 3), ["a"], DOCUMENT_TASK_TYPE)


def test_rejects_wrong_dimensions():
    with pytest.raises(ValueError, match="dims"):
        embed_texts(FakeClient(dims=3072), ["a"], DOCUMENT_TASK_TYPE)


def test_cache_roundtrip_and_config_change_invalidates(tmp_path, monkeypatch):
    path = tmp_path / "embeddings.json"
    save_cache(path, {"hash": [0.1, 0.2]})
    assert load_cache(path) == {"hash": [0.1, 0.2]}
    monkeypatch.setattr("indexer.cache.CONFIG", {"model": "other", "dimensions": 768})
    assert load_cache(path) == {}
