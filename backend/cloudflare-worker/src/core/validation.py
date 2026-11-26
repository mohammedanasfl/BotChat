"""Validation of the POST /api/chat request body."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from config.settings import Settings
from core.errors import ApiError, ErrorCode
from prompts.builder import Turn

MAX_HISTORY_ITEM_CHARS = 2000


@dataclass(frozen=True)
class ChatRequest:
    message: str
    history: list[Turn]
    conversation_id: str | None


def _invalid(detail: str) -> ApiError:
    return ApiError(ErrorCode.VALIDATION_ERROR, detail)


def parse_chat_request(data: dict[str, Any], settings: Settings) -> ChatRequest:
    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        raise _invalid("'message' must be a non-empty string.")
    message = message.strip()
    if len(message) > settings.max_message_chars:
        raise _invalid(f"'message' must be at most {settings.max_message_chars} characters.")

    raw_history = data.get("history", [])
    if not isinstance(raw_history, list):
        raise _invalid("'history' must be a list.")
    if len(raw_history) > settings.max_history_messages:
        raise _invalid(f"'history' must have at most {settings.max_history_messages} items.")
    history = []
    for item in raw_history:
        role = item.get("role") if isinstance(item, dict) else None
        content = item.get("content") if isinstance(item, dict) else None
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            raise _invalid("Each 'history' item needs role 'user' or 'assistant' and text content.")
        if len(content) > MAX_HISTORY_ITEM_CHARS:
            raise _invalid(f"'history' items must be at most {MAX_HISTORY_ITEM_CHARS} characters.")
        history.append(Turn(role, content))

    conversation_id = data.get("conversation_id")
    if conversation_id is not None:
        try:
            conversation_id = str(uuid.UUID(str(conversation_id)))
        except ValueError as exc:
            raise _invalid("'conversation_id' must be a UUID.") from exc
    return ChatRequest(message, history, conversation_id)
