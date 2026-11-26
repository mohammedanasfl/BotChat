import asyncio
from types import SimpleNamespace

import pytest

import routes.search as search_route
from app import dispatch
from config.embedding import EMBEDDING_DIMENSIONS
from services.embeddings import build_request, parse_response
from services.http import UpstreamError
from services.retrieval import filter_matches, index_status, search

# --- embeddings (request shape verified live in Phase 2) ---------------------------------


def test_embed_request_uses_top_level_fields():
    body = build_request("hi")
    assert body["taskType"] == "RETRIEVAL_QUERY"
    assert body["outputDimensionality"] == EMBEDDING_DIMENSIONS
    assert "embedContentConfig" not in body  # silently ignored by the API


def test_embed_response_must_have_expected_dimensions():
    assert len(parse_response({"embedding": {"values": [0.1] * EMBEDDING_DIMENSIONS}})) == 768
    with pytest.raises(UpstreamError, match="3072"):
        parse_response({"embedding": {"values": [0.1] * 3072}})
    with pytest.raises(UpstreamError):
        parse_response({})


# --- retrieval ---------------------------------------------------------------------------

MATCHES = [
    {
        "id": "company-004",
        "score": 0.64,
        "metadata": {"heading": "Company › Working hours", "text": "Mon-Sat"},
    },
    {
        "id": "company-005",
        "score": 0.57,
        "metadata": {"heading": "Company › Response time", "text": "24h"},
    },
    {"id": "broken", "score": 0.9, "metadata": {}},
]


def test_filter_keeps_only_matches_above_min_score_with_text():
    chunks = filter_matches(MATCHES, min_score=0.60)
    assert [(c.chunk_id, c.heading, c.text) for c in chunks] == [
        ("company-004", "Company › Working hours", "Mon-Sat")
    ]


class FakeIndex:
    def __init__(self, info=None):
        self.calls = []
        self.info = info or {"dimensions": 768, "vectorCount": 34}

    async def query(self, vector, options):
        self.calls.append((len(vector), options))
        return {"matches": MATCHES}

    async def describe(self):
        return self.info


def test_search_queries_binding_with_options():
    index = FakeIndex()
    chunks = asyncio.run(search(index, [0.1] * 768, top_k=4, min_score=0.5))
    assert index.calls == [(768, {"topK": 4, "returnMetadata": "all"})]
    assert [c.chunk_id for c in chunks] == ["company-004", "company-005"]


@pytest.mark.parametrize(
    ("info", "ready"),
    [
        ({"dimensions": 768, "vectorCount": 34}, True),
        ({"config": {"dimensions": 768}, "vectorsCount": 34}, True),
        ({"dimensions": 3072, "vectorCount": 34}, False),
        ({"dimensions": 768, "vectorCount": 0}, False),
    ],
)
def test_index_status(info, ready):
    assert index_status(info)[0] is ready


# --- routes ------------------------------------------------------------------------------


def env(**overrides):
    base = dict(ENVIRONMENT="development", GEMINI_API_KEY="test-key", VECTORIZE=FakeIndex())
    return SimpleNamespace(**{**base, **overrides})


def call(method, path, env_, body=""):
    return asyncio.run(dispatch(method, f"http://localhost{path}", {}, env_, "r_t", body))


def test_dev_search_returns_filtered_results(monkeypatch):
    async def fake_embed(text, key):
        assert key == "test-key"
        return [0.1] * 768

    monkeypatch.setattr(search_route, "embed_query", fake_embed)
    result = call("POST", "/api/dev/search", env(), '{"query": "open on Sunday?"}')
    assert result.status == 200
    assert [r["chunk_id"] for r in result.body["results"]] == ["company-004"]


def test_dev_search_is_hidden_in_production():
    prod = env(ENVIRONMENT="production", ALLOWED_ORIGINS="https://a.example")
    assert call("POST", "/api/dev/search", prod, '{"query": "x"}').status == 404


@pytest.mark.parametrize("body", ["not json", "[]", '{"query": ""}', '{"query": 5}'])
def test_dev_search_validates_input(body):
    assert call("POST", "/api/dev/search", env(), body).status in (400, 422)


def test_dev_search_upstream_failure_is_503(monkeypatch):
    async def failing(text, key):
        raise UpstreamError("gemini-embed", "HTTP 429", status=429)

    monkeypatch.setattr(search_route, "embed_query", failing)
    result = call("POST", "/api/dev/search", env(), '{"query": "hi"}')
    assert result.status == 503
    assert result.body["error"]["code"] == "upstream_unavailable"


def test_missing_gemini_key_is_generic_500(monkeypatch):
    result = call("POST", "/api/dev/search", env(GEMINI_API_KEY=""), '{"query": "hi"}')
    assert result.status == 500


def test_ready_reports_not_ready_for_empty_index(capsys):
    empty = env(VECTORIZE=FakeIndex({"dimensions": 768, "vectorCount": 0}))
    result = call("GET", "/api/health/ready", empty)
    assert result.status == 503
    assert result.body == {"status": "not_ready"}  # no internals exposed
    assert "index is empty" in capsys.readouterr().err


def test_gemini_key_is_not_in_settings_repr():
    from config.settings import Settings

    assert "test-key" not in repr(Settings.from_env(env()))
