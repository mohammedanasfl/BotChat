from types import SimpleNamespace

import pytest

from config.settings import Settings
from core.errors import ApiError
from core.validation import parse_chat_request

SETTINGS = Settings.from_env(SimpleNamespace(ENVIRONMENT="development"))


def parse(**data):
    return parse_chat_request(data, SETTINGS)


def test_valid_request_is_normalized():
    req = parse(
        message="  Hi there  ",
        history=[{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi!"}],
        conversation_id="3F8A6C2E-6A1B-4F43-9A51-0C6E2F9D1B77",
        extra="ignored",
    )
    assert req.message == "Hi there"
    assert [(t.role, t.content) for t in req.history] == [("user", "Hello"), ("assistant", "Hi!")]
    assert req.conversation_id == "3f8a6c2e-6a1b-4f43-9a51-0c6e2f9d1b77"


def test_history_and_conversation_id_are_optional():
    req = parse(message="hi")
    assert req.history == [] and req.conversation_id is None


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ({}, "'message'"),
        ({"message": "   "}, "'message'"),
        ({"message": 42}, "'message'"),
        ({"message": "x" * 1001}, "at most 1000"),
        ({"message": "hi", "history": "nope"}, "list"),
        ({"message": "hi", "history": [{"role": "user", "content": "x"}] * 11}, "at most 10"),
        ({"message": "hi", "history": [{"role": "system", "content": "x"}]}, "role"),
        ({"message": "hi", "history": [{"role": "user", "content": ""}]}, "role"),
        ({"message": "hi", "history": ["text"]}, "role"),
        ({"message": "hi", "history": [{"role": "user", "content": "x" * 2001}]}, "2000"),
        ({"message": "hi", "conversation_id": "not-a-uuid"}, "UUID"),
    ],
)
def test_invalid_requests(data, fragment):
    with pytest.raises(ApiError) as exc:
        parse_chat_request(data, SETTINGS)
    assert exc.value.code == "validation_error"
    assert fragment in exc.value.message
