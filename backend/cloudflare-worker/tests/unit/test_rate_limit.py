import asyncio
import json
from types import SimpleNamespace

import pytest

import routes.session as session_route
from app import dispatch
from core.rate_limit import count_hit
from core.sse import StreamResult
from services.tokens import issue_token
from tests.unit.conftest import FakeRateLimiter, collect, stub_gemini

KEY = "k" * 48


class EmptyIndex:
    async def query(self, vector, options):
        return {"matches": []}


@pytest.fixture
def env(monkeypatch):
    stub_gemini(monkeypatch)

    async def fake_siteverify(token, secret, ip):
        return {"success": True, "hostname": "example.com"}

    monkeypatch.setattr(session_route, "siteverify", fake_siteverify)
    return SimpleNamespace(
        ENVIRONMENT="development",
        TURNSTILE_ALLOWED_HOSTNAMES="example.com",
        TURNSTILE_SECRET_KEY="t",
        SESSION_SIGNING_KEY=KEY,
        GEMINI_API_KEY="g",
        VECTORIZE=EmptyIndex(),
        RATE_LIMITER=FakeRateLimiter(),
    )


class Done:
    status = 200


def post(env, path, body, ip="1.1.1.1", token=None):
    headers = {"CF-Connecting-IP": ip}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    result = asyncio.run(dispatch("POST", f"http://l{path}", headers, env, "r", json.dumps(body)))
    if isinstance(result, StreamResult):
        collect(result)  # drain the stream like a client would
        return Done()
    return result


def test_session_limit_per_ip(env):
    statuses = [post(env, "/api/session", {"turnstile_token": "t"}).status for _ in range(6)]
    assert statuses == [200] * 5 + [429]
    blocked = post(env, "/api/session", {"turnstile_token": "t"})
    assert blocked.headers["retry-after"] == "60"
    assert blocked.body["error"]["code"] == "rate_limited"
    assert post(env, "/api/session", {"turnstile_token": "t"}, ip="2.2.2.2").status == 200


def test_chat_limit_per_session(env):
    token, claims = issue_token(KEY, 900)
    statuses = [post(env, "/api/chat", {"message": "hi"}, token=token).status for _ in range(9)]
    assert statuses == [200] * 8 + [429]
    assert env.RATE_LIMITER.keys("chat-session") == {claims["sub"]}


def test_chat_limit_per_ip_applies_before_auth(env):
    statuses = [post(env, "/api/chat", {"message": "hi"}).status for _ in range(21)]
    assert statuses == [401] * 20 + [429]  # floods of bad tokens get cut off too
    assert env.RATE_LIMITER.keys("chat-session") == set()  # invalid tokens never reach it


def test_missing_ip_header_uses_local_key(env):
    asyncio.run(dispatch("POST", "http://l/api/session", {}, env, "r", '{"turnstile_token":"t"}'))
    assert env.RATE_LIMITER.keys("session-ip") == {"local"}


def test_body_too_large_flag_rejected_with_cors(env):
    env.ALLOWED_ORIGINS = "http://localhost:5173"
    headers = {"Origin": "http://localhost:5173"}
    result = asyncio.run(
        dispatch("POST", "http://l/api/chat", headers, env, "r", "", body_too_large=True)
    )
    assert result.status == 413
    assert result.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_chat_completed_is_logged_without_message_text(env, capsys):
    token, _ = issue_token(KEY, 900)
    post(env, "/api/chat", {"message": "my secret question"}, token=token)
    out = capsys.readouterr().out
    assert '"event":"chat_completed"' in out
    assert "my secret question" not in out
    assert "1.1.1.1" not in out


def test_limits_come_from_config(env):
    env.RATE_LIMIT_SESSION_IP = "2"
    statuses = [post(env, "/api/session", {"turnstile_token": "t"}).status for _ in range(3)]
    assert statuses == [200, 200, 429]


# --- fixed-window counter (runs inside the Durable Object) --------------------------------


def test_count_hit_increments_within_window():
    state, count = count_hit(None, now=120.0, period=60)
    assert count == 1
    state, count = count_hit(state, now=150.0, period=60)
    assert count == 2


def test_count_hit_resets_in_new_window():
    state, _ = count_hit(None, now=100.0, period=60)
    state, _ = count_hit(state, now=110.0, period=60)
    _, count = count_hit(state, now=180.0, period=60)  # window 3 vs window 1
    assert count == 1
