import asyncio
from types import SimpleNamespace

from app import dispatch

ALLOWED = "https://abinayagarment.dentcare-demo.workers.dev"
ENV = SimpleNamespace(ENVIRONMENT="production", ALLOWED_ORIGINS=ALLOWED)


def run(method, path, origin=None, body=""):
    headers = {"Origin": origin} if origin else {}
    return asyncio.run(dispatch(method, f"https://api.test{path}", headers, ENV, "r_t", body))


def test_allowed_origin_gets_cors_headers():
    result = run("GET", "/api/health", origin=ALLOWED)
    assert result.status == 200
    assert result.headers["access-control-allow-origin"] == ALLOWED
    assert result.headers["vary"] == "Origin"


def test_disallowed_origin_is_rejected_without_cors_headers():
    result = run("GET", "/api/health", origin="https://evil.example")
    assert result.status == 403
    assert result.body["error"]["code"] == "forbidden_origin"
    assert "access-control-allow-origin" not in result.headers


def test_no_origin_header_is_allowed():
    result = run("GET", "/api/health")
    assert result.status == 200
    assert "access-control-allow-origin" not in result.headers


def test_preflight_returns_204_without_body():
    result = run("OPTIONS", "/api/chat", origin=ALLOWED)
    assert result.status == 204
    assert result.encoded_body() is None
    assert "POST" in result.headers["access-control-allow-methods"]
    assert "Authorization" in result.headers["access-control-allow-headers"]
    assert result.headers["access-control-allow-origin"] == ALLOWED


def test_errors_also_carry_cors_headers_for_allowed_origin():
    result = run("GET", "/api/nope", origin=ALLOWED)
    assert result.status == 404
    assert result.headers["access-control-allow-origin"] == ALLOWED


def test_oversized_body_is_rejected():
    env_body = "x" * 40_000
    result = run("POST", "/api/dev/search", body=env_body)
    assert result.status == 413
