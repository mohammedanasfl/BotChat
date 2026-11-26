"""Streaming answer generation with Gemini `streamGenerateContent?alt=sse`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from core.sse import SSEParser
from services.embeddings import GEMINI_BASE
from services.http import UpstreamError

STREAM_TIMEOUT_MS = 30_000
FINISH_REASONS = {"STOP": "stop", "MAX_TOKENS": "max_tokens", "SAFETY": "safety"}
BLOCKED_MESSAGE = "Sorry, I can't help with that request."


@dataclass
class StreamState:
    """What a finished stream produced (filled in while iterating)."""

    finish_reason: str = "other"
    usage: dict[str, int] = field(default_factory=dict)
    emitted_text: bool = False


def deltas_from_chunk(chunk: dict[str, Any], state: StreamState) -> list[str]:
    """Extract answer text from one Gemini stream chunk and update `state` (pure)."""
    usage = chunk.get("usageMetadata")
    if isinstance(usage, dict):
        state.usage = {k: v for k, v in usage.items() if isinstance(v, int)}
    if (chunk.get("promptFeedback") or {}).get("blockReason"):
        state.finish_reason = "safety"
        return [BLOCKED_MESSAGE]
    candidates = chunk.get("candidates") or []
    if not candidates:
        return []
    candidate = candidates[0]
    if candidate.get("finishReason"):
        state.finish_reason = FINISH_REASONS.get(candidate["finishReason"], "other")
    parts = (candidate.get("content") or {}).get("parts") or []
    texts = [p["text"] for p in parts if p.get("text") and not p.get("thought")]
    if not texts and state.finish_reason == "safety" and not state.emitted_text:
        texts = [BLOCKED_MESSAGE]
    return texts


async def open_stream(request: dict[str, Any], *, model: str, api_key: str, abort_signal: Any):
    """Start the Gemini stream. Raises UpstreamError (-> JSON 503) if Gemini rejects it.

    Opening before the HTTP response starts means an immediate failure (bad key, quota) is a
    normal JSON error, and only mid-stream failures become an SSE `error` event.
    """
    import json

    from js import AbortSignal
    from pyodide.ffi import to_js
    from workers import fetch

    signals = [AbortSignal.timeout(STREAM_TIMEOUT_MS)]
    if abort_signal is not None:
        signals.append(abort_signal)  # visitor disconnected -> stop generating (and paying)
    try:
        response = await fetch(
            f"{GEMINI_BASE}/models/{model}:streamGenerateContent?alt=sse",
            method="POST",
            headers={"content-type": "application/json", "x-goog-api-key": api_key},
            body=json.dumps(request),
            signal=AbortSignal.any(to_js(signals)),
        )
    except Exception as exc:
        detail = f"request failed: {type(exc).__name__}: {str(exc)[:120]}"
        raise UpstreamError("gemini-stream", detail) from exc
    if response.status != 200:
        raise UpstreamError("gemini-stream", f"HTTP {response.status}", status=response.status)
    return response


async def iter_deltas(response: Any, state: StreamState) -> AsyncIterator[str]:
    """Yield answer text deltas as Gemini streams them."""
    import codecs

    decoder = codecs.getincrementaldecoder("utf-8")()  # multi-byte chars may span chunks
    parser = SSEParser()
    async for raw in response.body:
        for chunk in parser.feed(decoder.decode(raw.to_bytes())):
            for text in deltas_from_chunk(chunk, state):
                state.emitted_text = True
                yield text
