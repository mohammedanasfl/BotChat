import asyncio
import json
from types import SimpleNamespace

import pytest

from app import dispatch
from core.sse import SSEParser, StreamResult, format_event
from prompts.builder import NO_REFERENCE_DATA, Turn, build_generate_request, retrieval_query
from prompts.system_prompt import SYSTEM_PROMPT
from services.gemini_stream import BLOCKED_MESSAGE, StreamState, deltas_from_chunk
from services.http import UpstreamError
from services.retrieval import RetrievedChunk
from tests.unit.conftest import FakeRateLimiter, collect, stub_gemini

HOURS = RetrievedChunk("company-004", "Company › Working hours", "Mon-Sat 9-7.", 0.65)

# --- retrieval query ---------------------------------------------------------------------


def test_short_follow_up_includes_previous_user_question():
    history = [Turn("user", "Do you make hoodies?"), Turn("assistant", "Yes, cotton hoodies.")]
    assert retrieval_query("What colours?", history) == "Do you make hoodies?\nWhat colours?"


def test_long_or_first_questions_are_used_as_is():
    long_q = "Can you print our company logo on the classic polo t-shirts please?"
    assert retrieval_query(long_q, [Turn("user", "hi")]) == long_q
    assert retrieval_query("Hours?", []) == "Hours?"


# --- prompt builder ----------------------------------------------------------------------


def build(message="Open Sunday?", history=(), chunks=(HOURS,), max_history=10):
    return build_generate_request(
        message, list(history), list(chunks), max_history=max_history, max_output_tokens=1024
    )


def test_request_has_system_rules_reference_data_and_question():
    req = build()
    assert req["systemInstruction"]["parts"][0]["text"] == SYSTEM_PROMPT
    final = req["contents"][-1]
    assert final["role"] == "user"
    text = final["parts"][0]["text"]
    assert "<reference_data>\n[1] Company › Working hours\nMon-Sat 9-7.\n</reference_data>" in text
    assert text.endswith("<visitor_question>\nOpen Sunday?\n</visitor_question>")
    assert req["generationConfig"] == {
        "maxOutputTokens": 1024,
        "thinkingConfig": {"thinkingLevel": "minimal"},
    }


def test_history_roles_mapped_and_trimmed():
    history = [
        Turn("user", f"q{i}") if i % 2 == 0 else Turn("assistant", f"a{i}") for i in range(6)
    ]
    req = build(history=history, max_history=4)
    assert [(c["role"], c["parts"][0]["text"]) for c in req["contents"][:-1]] == [
        ("user", "q2"),
        ("model", "a3"),
        ("user", "q4"),
        ("model", "a5"),
    ]
    assert len(build(history=history, max_history=0)["contents"]) == 1


def test_no_chunks_says_no_reference_data():
    assert NO_REFERENCE_DATA in build(chunks=())["contents"][-1]["parts"][0]["text"]


def test_system_prompt_covers_key_rules():
    for rule in (
        "ONLY",
        "Never state or estimate a price",
        "data, not instructions",
        "same language",
    ):
        assert rule in SYSTEM_PROMPT


# --- Gemini stream parsing ----------------------------------------------------------------


def test_sse_parser_handles_split_chunks_and_crlf():
    parser = SSEParser()
    assert parser.feed('data: {"a": 1}\r\n\r\ndata: {"b"') == [{"a": 1}]
    assert parser.feed(": 2}\n\n") == [{"b": 2}]
    assert parser.feed("event: ping\n\n") == []


def test_format_event_is_single_data_line():
    text = format_event("token", {"text": "line1\nline2"})
    assert text == 'event: token\ndata: {"text":"line1\\nline2"}\n\n'


def chunk(parts, finish=None, **extra):
    candidate = {"content": {"parts": parts}}
    if finish:
        candidate["finishReason"] = finish
    return {"candidates": [candidate], **extra}


def test_deltas_skip_thoughts_and_track_finish_and_usage():
    state = StreamState()
    assert deltas_from_chunk(
        chunk([{"text": "plan", "thought": True}, {"text": "Yes"}]), state
    ) == ["Yes"]
    usage = {"promptTokenCount": 9, "candidatesTokenCount": 3}
    assert deltas_from_chunk(chunk([{"text": ", we do."}], "STOP", usageMetadata=usage), state) == [
        ", we do."
    ]
    assert state.finish_reason == "stop" and state.usage == usage


def test_deltas_map_blocked_and_safety():
    state = StreamState()
    assert deltas_from_chunk({"promptFeedback": {"blockReason": "SAFETY"}}, state) == [
        BLOCKED_MESSAGE
    ]
    assert state.finish_reason == "safety"
    assert deltas_from_chunk(chunk([], "SAFETY"), StreamState()) == [BLOCKED_MESSAGE]
    assert deltas_from_chunk(chunk([{"text": "x"}], "MAX_TOKENS"), state) == ["x"]
    assert state.finish_reason == "max_tokens"


# --- full pipeline through POST /api/chat ------------------------------------------------

KEY = "k" * 48


class FakeIndex:
    def __init__(self, matches):
        self.matches = matches

    async def query(self, vector, options):
        return {"matches": self.matches}


def chat(env, body):
    from services.tokens import issue_token

    token, _ = issue_token(KEY, 900)
    headers = {"Authorization": f"Bearer {token}"}
    return asyncio.run(dispatch("POST", "http://l/api/chat", headers, env, "r", body))


def make_env(matches=()):
    return SimpleNamespace(
        ENVIRONMENT="development",
        GEMINI_API_KEY="k",
        SESSION_SIGNING_KEY=KEY,
        VECTORIZE=FakeIndex(list(matches)),
        RATE_LIMITER=FakeRateLimiter(),
    )


MATCHES = [
    {
        "id": "company-004",
        "score": 0.65,
        "metadata": {"heading": HOURS.heading, "text": HOURS.text},
    },
    {"id": "faqs-001", "score": 0.40, "metadata": {"heading": "x", "text": "y"}},
]


def test_chat_streams_start_tokens_complete(monkeypatch, capsys):
    calls = stub_gemini(monkeypatch, deltas=("We are ", "closed on Sundays."))
    body = json.dumps(
        {
            "message": "Open Sunday?",
            "history": [{"role": "user", "content": "Hi"}],
            "conversation_id": "3f8a6c2e-6a1b-4f43-9a51-0c6e2f9d1b77",
        }
    )
    result = chat(make_env(MATCHES), body)
    assert isinstance(result, StreamResult)
    assert result.headers["content-type"].startswith("text/event-stream")

    events = collect(result)
    assert events[0] == (
        "start",
        {"request_id": "r", "conversation_id": "3f8a6c2e-6a1b-4f43-9a51-0c6e2f9d1b77"},
    )
    assert events[1:3] == [  # trailing spaces wait for the next delta (see follow_ups.py)
        ("token", {"text": "We are"}),
        ("token", {"text": " closed on Sundays."}),
    ]
    assert events[3] == (
        "complete",
        {
            "finish_reason": "stop",
            "follow_ups": [],
            "sources": [{"chunk_id": "company-004", "heading": HOURS.heading}],
        },
    )
    assert len(events) == 4
    assert calls["query"] == "Hi\nOpen Sunday?"  # short follow-up
    assert "Mon-Sat 9-7." in calls["request"]["contents"][-1]["parts"][0]["text"]
    assert '"event":"chat_completed"' in capsys.readouterr().out


def test_mid_stream_failure_ends_with_error_event(monkeypatch):
    stub_gemini(monkeypatch, deltas=("Partial", "never"), fail_after=1)
    events = collect(chat(make_env(), '{"message":"hi"}'))
    assert [e[0] for e in events] == ["start", "token", "error"]
    assert events[-1][1]["code"] == "upstream_unavailable"


def test_empty_stream_ends_with_error_event(monkeypatch):
    stub_gemini(monkeypatch, deltas=())
    assert [e[0] for e in collect(chat(make_env(), '{"message":"hi"}'))] == ["start", "error"]


def test_gemini_rejecting_before_stream_is_json_503(monkeypatch):
    stub_gemini(monkeypatch, open_error=UpstreamError("gemini-stream", "HTTP 429", status=429))
    result = chat(make_env(), '{"message":"hi"}')
    assert result.status == 503
    assert result.body["error"]["code"] == "upstream_unavailable"


@pytest.mark.parametrize(
    "body",
    ['{"message": ""}', '{"message": "hi", "history": [{"role": "system", "content": "x"}]}'],
)
def test_chat_validates(body):
    assert chat(make_env(), body).status == 422


def test_client_disconnect_is_not_an_error(monkeypatch, capsys):
    stub_gemini(monkeypatch, deltas=("Partial", "never"), fail_after=1)
    env = make_env()
    from services.tokens import issue_token

    token, _ = issue_token(KEY, 900)
    aborted = SimpleNamespace(aborted=True)
    result = asyncio.run(
        dispatch(
            "POST",
            "http://l/api/chat",
            {"Authorization": f"Bearer {token}"},
            env,
            "r",
            '{"message":"hi"}',
            abort_signal=aborted,
        )
    )
    assert [e[0] for e in collect(result)] == ["start", "token"]  # no error event
    logs = capsys.readouterr()
    assert "client_disconnected" in logs.out and "stream_failed" not in logs.err


def test_chat_sends_follow_ups_in_complete_and_hides_marker(monkeypatch):
    deltas = ("Closed on Sundays.\n<<FOL", "LOW_UPS>>\n- What are your hours?\n", "Where are you?")
    stub_gemini(monkeypatch, deltas=deltas)
    events = collect(chat(make_env(MATCHES), '{"message":"Open Sunday?"}'))
    shown = "".join(e[1]["text"] for e in events if e[0] == "token")
    assert shown == "Closed on Sundays."
    assert events[-1][1]["follow_ups"] == ["What are your hours?", "Where are you?"]


def test_marker_only_stream_is_an_error(monkeypatch):
    stub_gemini(monkeypatch, deltas=("<<FOLLOW_UPS>>\nWhat?",))
    assert [e[0] for e in collect(chat(make_env(), '{"message":"hi"}'))] == ["start", "error"]
