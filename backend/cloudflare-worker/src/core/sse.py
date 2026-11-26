"""Server-Sent Events: formatting our events and parsing Gemini's stream (pure Python)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

SSE_HEADERS = {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    "x-accel-buffering": "no",
}


def format_event(event: str, data: dict[str, Any]) -> str:
    """One SSE event: `event: <name>\\ndata: <json>\\n\\n` (JSON never contains raw newlines)."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


class SSEParser:
    """Incremental parser for an upstream SSE byte stream (Gemini `alt=sse`).

    Feed raw chunks as they arrive; complete events are returned as decoded JSON payloads.
    Handles events split across chunks, CRLF or LF line endings, and multi-line `data:`.
    """

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, chunk: str) -> list[dict[str, Any]]:
        self._buffer += chunk.replace("\r\n", "\n")
        events = []
        while "\n\n" in self._buffer:
            block, self._buffer = self._buffer.split("\n\n", 1)
            data = "\n".join(
                line[5:].lstrip() for line in block.split("\n") if line.startswith("data:")
            )
            if data and data != "[DONE]":
                events.append(json.loads(data))
        return events


@dataclass
class StreamResult:
    """A streaming HTTP response: `events` yields already-formatted SSE text."""

    events: AsyncIterator[str]
    status: int = 200
    headers: dict[str, str] = field(default_factory=lambda: dict(SSE_HEADERS))
