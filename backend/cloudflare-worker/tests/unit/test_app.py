"""End-to-end tests of the pure dispatch layer (everything except the runtime adapter)."""

import asyncio
import json
import re
from types import SimpleNamespace

from app import dispatch
from config.embedding import (
    EMBEDDING_DIMENSIONS,
    VECTORIZE_MAX_DIMENSIONS,
    validate_embedding_config,
)
from core.context import new_request_id
from core.responses import JsonResult, finalize_headers

DEV_ENV = SimpleNamespace(ENVIRONMENT="development", ALLOWED_ORIGINS="http://localhost:5173")


def run(method, url, env=DEV_ENV, headers=None):
    return asyncio.run(dispatch(method, url, headers or {}, env, "r_test"))


def test_health_ok():
    result = run("GET", "http://localhost:8787/api/health")
    assert result.status == 200
    assert result.body == {"status": "ok", "version": "0.1.0"}


def test_unknown_path_returns_error_envelope():
    result = run("GET", "http://localhost:8787/nope?x=1")
    assert result.status == 404
    assert result.body["error"]["code"] == "not_found"
    assert result.body["request_id"] == "r_test"


def test_wrong_method_returns_405():
    result = run("DELETE", "http://localhost:8787/api/health")
    assert result.status == 405
    assert result.headers["allow"] == "GET"


def test_config_error_becomes_generic_500(capsys):
    broken = SimpleNamespace(ENVIRONMENT="production", ALLOWED_ORIGINS="http://insecure.example")
    result = run("GET", "http://localhost:8787/api/health", env=broken)
    assert result.status == 500
    assert result.body["error"] == {
        "code": "internal_error",
        "message": "Something went wrong. Please try again.",
    }
    # Details go to logs, never to the client.
    assert "https" not in json.dumps(result.body)
    assert "config_error" in capsys.readouterr().err


def test_unhandled_exception_is_contained(monkeypatch, capsys):
    import routes

    def boom(_ctx):
        raise RuntimeError("secret internal detail")

    monkeypatch.setitem(routes.ROUTES, "/api/boom", {"GET": boom})
    result = run("GET", "http://localhost:8787/api/boom")
    assert result.status == 500
    assert "secret internal detail" not in json.dumps(result.body)
    assert "secret internal detail" not in capsys.readouterr().err


def test_async_handlers_are_awaited(monkeypatch):
    import routes

    async def slow(_ctx):
        await asyncio.sleep(0)
        return JsonResult(status=202, body={"ok": True})

    monkeypatch.setitem(routes.ROUTES, "/api/async", {"GET": slow})
    assert run("GET", "http://localhost:8787/api/async").status == 202


def test_finalize_headers_adds_security_and_request_id():
    headers = finalize_headers(JsonResult(200, {}, {"Retry-After": "5"}), "r_1")
    assert headers["content-type"] == "application/json; charset=utf-8"
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-request-id"] == "r_1"
    assert headers["retry-after"] == "5"


def test_request_ids_are_unique_and_well_formed():
    ids = {new_request_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(re.fullmatch(r"r_[0-9a-f]{12}", i) for i in ids)


def test_embedding_config_fits_vectorize():
    validate_embedding_config()
    assert EMBEDDING_DIMENSIONS <= VECTORIZE_MAX_DIMENSIONS
