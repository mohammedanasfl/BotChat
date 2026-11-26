import asyncio
import json
from types import SimpleNamespace

import pytest

import routes.session as session_route
from app import dispatch
from services import embeddings, gemini_client
from services.http import UpstreamError
from services.tokens import issue_token
from services.turnstile import check_result
from tests.unit.conftest import FakeRateLimiter

KEY = "k" * 48
HOST = "abinayagarment.dentcare-demo.workers.dev"


def env(**overrides):
    base = dict(
        ENVIRONMENT="development",
        TURNSTILE_ALLOWED_HOSTNAMES=f"{HOST},example.com",
        TURNSTILE_SECRET_KEY="ts-secret",
        SESSION_SIGNING_KEY=KEY,
        GEMINI_API_KEY="g",
        VECTORIZE=SimpleNamespace(),
        RATE_LIMITER=FakeRateLimiter(),
    )
    return SimpleNamespace(**{**base, **overrides})


def call(method, path, env_, body="", headers=None):
    return asyncio.run(dispatch(method, f"http://l{path}", headers or {}, env_, "r", body))


# --- siteverify result checks ------------------------------------------------------------

OK = {"success": True, "hostname": HOST, "action": "chat_session"}


@pytest.mark.parametrize(
    ("result", "require_action", "ok"),
    [
        (OK, True, True),
        ({"success": False, "error-codes": ["invalid-input-response"]}, False, False),
        ({**OK, "hostname": "evil.example"}, False, False),
        ({**OK, "action": "other"}, False, False),
        ({"success": True, "hostname": HOST}, False, True),  # test keys send no action
        ({"success": True, "hostname": HOST}, True, False),  # production requires it
    ],
)
def test_check_result(result, require_action, ok):
    assert (check_result(result, (HOST,), require_action=require_action) is None) is ok


def test_bad_secret_is_a_config_error_not_a_visitor_failure():
    from config.settings import ConfigError

    with pytest.raises(ConfigError):
        check_result(
            {"success": False, "error-codes": ["invalid-input-secret"]},
            (HOST,),
            require_action=True,
        )


def test_session_with_rejected_secret_is_generic_500(monkeypatch):
    monkeypatch.setattr(
        session_route,
        "siteverify",
        fake_siteverify({"success": False, "error-codes": ["invalid-input-secret"]}),
    )
    assert call("POST", "/api/session", env(), '{"turnstile_token": "t"}').status == 500


# --- POST /api/session -------------------------------------------------------------------


def fake_siteverify(result):
    async def _verify(token, secret, remote_ip):
        _verify.args = (token, secret, remote_ip)
        return result

    return _verify


def test_session_issued_for_valid_turnstile(monkeypatch):
    verify = fake_siteverify(OK)
    monkeypatch.setattr(session_route, "siteverify", verify)
    result = call(
        "POST", "/api/session", env(), '{"turnstile_token": "tok"}', {"CF-Connecting-IP": "1.2.3.4"}
    )
    assert result.status == 200
    assert result.body["token_type"] == "Bearer" and result.body["expires_in"] == 900
    assert result.body["expires_at"].endswith("Z")
    assert verify.args == ("tok", "ts-secret", "1.2.3.4")


def test_session_rejected_for_failed_turnstile(monkeypatch, capsys):
    monkeypatch.setattr(
        session_route, "siteverify", fake_siteverify({"success": False, "error-codes": ["x"]})
    )
    result = call("POST", "/api/session", env(), '{"turnstile_token": "bad"}')
    assert result.status == 403
    assert result.body["error"]["code"] == "turnstile_failed"
    assert "turnstile_failed" in capsys.readouterr().err  # reason logged, not returned


def test_session_fails_closed_when_turnstile_unreachable(monkeypatch):
    async def down(*_args):
        raise UpstreamError("turnstile", "timeout")

    monkeypatch.setattr(session_route, "siteverify", down)
    assert call("POST", "/api/session", env(), '{"turnstile_token": "t"}').status == 503


@pytest.mark.parametrize(
    "body", ["{}", '{"turnstile_token": ""}', json.dumps({"turnstile_token": "x" * 3000})]
)
def test_session_validates_token_field(body):
    assert call("POST", "/api/session", env(), body).status == 422


def test_session_missing_secret_is_generic_500():
    assert (
        call(
            "POST", "/api/session", env(TURNSTILE_SECRET_KEY=""), '{"turnstile_token": "t"}'
        ).status
        == 500
    )


# --- POST /api/chat authentication ---------------------------------------------------------


def stub_rag(monkeypatch):
    async def fake_embed(text, key):
        return [0.1] * 768

    async def fake_generate(request, *, model, api_key):
        return gemini_client.Generation("Hello!", "stop", {})

    class Index:
        async def query(self, vector, options):
            return {"matches": []}

    monkeypatch.setattr(embeddings, "embed_query", fake_embed)
    monkeypatch.setattr(gemini_client, "generate", fake_generate)
    return env(VECTORIZE=Index())


def chat(env_, auth=None):
    headers = {"Authorization": auth} if auth else {}
    return call("POST", "/api/chat", env_, '{"message": "hi"}', headers)


def test_chat_with_valid_session(monkeypatch):
    token, _ = issue_token(KEY, 900)
    result = chat(stub_rag(monkeypatch), f"Bearer {token}")
    assert result.status == 200
    assert result.body["answer"] == "Hello!"


@pytest.mark.parametrize("auth", [None, "Bearer", "Basic abc", "Bearer not.a.jwt"])
def test_chat_rejects_missing_or_invalid_token(monkeypatch, auth):
    result = chat(stub_rag(monkeypatch), auth)
    assert result.status == 401
    assert result.body["error"]["code"] == "unauthorized"


def test_chat_rejects_token_signed_with_other_key(monkeypatch):
    token, _ = issue_token("other-key", 900)
    assert chat(stub_rag(monkeypatch), f"Bearer {token}").status == 401


def test_chat_expired_token_returns_session_expired(monkeypatch):
    token, _ = issue_token(KEY, 60, now=1_000_000)
    result = chat(stub_rag(monkeypatch), f"Bearer {token}")
    assert result.status == 401
    assert result.body["error"]["code"] == "session_expired"


def test_production_requires_turnstile_hostnames():
    prod = env(
        ENVIRONMENT="production", ALLOWED_ORIGINS=f"https://{HOST}", TURNSTILE_ALLOWED_HOSTNAMES=""
    )
    assert call("GET", "/api/health", prod).status == 500


def test_secrets_not_in_settings_repr():
    from config.settings import Settings

    text = repr(Settings.from_env(env()))
    assert "ts-secret" not in text and KEY not in text
