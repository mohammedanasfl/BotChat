"""Gemini answer generation (non-streaming; streaming is added in Phase 8)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.embeddings import GEMINI_BASE
from services.http import UpstreamError, request_json

FINISH_REASONS = {"STOP": "stop", "MAX_TOKENS": "max_tokens", "SAFETY": "safety"}
BLOCKED_MESSAGE = "Sorry, I can't help with that request."


@dataclass(frozen=True)
class Generation:
    text: str
    finish_reason: str  # stop | max_tokens | safety | other
    usage: dict[str, int]


def parse_generation(data: dict[str, Any]) -> Generation:
    usage = {k: v for k, v in (data.get("usageMetadata") or {}).items() if isinstance(v, int)}
    if (data.get("promptFeedback") or {}).get("blockReason"):
        return Generation(BLOCKED_MESSAGE, "safety", usage)

    candidates = data.get("candidates") or []
    if not candidates:
        raise UpstreamError("gemini-generate", "no candidates in response")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    finish = FINISH_REASONS.get(candidate.get("finishReason", ""), "other")
    if not text:
        if finish == "safety":
            return Generation(BLOCKED_MESSAGE, finish, usage)
        raise UpstreamError("gemini-generate", f"empty answer (finish={finish})")
    return Generation(text, finish, usage)


async def generate(request: dict[str, Any], *, model: str, api_key: str) -> Generation:
    data = await request_json(
        "gemini-generate",
        f"{GEMINI_BASE}/models/{model}:generateContent",
        method="POST",
        headers={"x-goog-api-key": api_key},
        body=request,
        timeout_ms=25_000,
    )
    return parse_generation(data)
