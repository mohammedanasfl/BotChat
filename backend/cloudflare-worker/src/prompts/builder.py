"""Build the Gemini request and the retrieval query (pure functions)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prompts.system_prompt import SYSTEM_PROMPT
from services.retrieval import RetrievedChunk

FOLLOW_UP_MAX_WORDS = 6
NO_REFERENCE_DATA = "(no relevant reference data found)"


@dataclass(frozen=True)
class Turn:
    role: str  # "user" or "assistant"
    content: str


def retrieval_query(message: str, history: list[Turn]) -> str:
    """Short follow-ups ("what colours?") lack context, so prepend the previous user question."""
    if len(message.split()) > FOLLOW_UP_MAX_WORDS:
        return message
    previous = next((t.content for t in reversed(history) if t.role == "user"), None)
    return f"{previous}\n{message}" if previous else message


def reference_block(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return NO_REFERENCE_DATA
    return "\n\n".join(f"[{i}] {c.heading}\n{c.text}" for i, c in enumerate(chunks, start=1))


def build_generate_request(
    message: str,
    history: list[Turn],
    chunks: list[RetrievedChunk],
    *,
    max_history: int,
    max_output_tokens: int,
) -> dict[str, Any]:
    recent = history[-max_history:] if max_history else []
    contents = [
        {"role": "model" if t.role == "assistant" else "user", "parts": [{"text": t.content}]}
        for t in recent
    ]
    final_turn = (
        f"<reference_data>\n{reference_block(chunks)}\n</reference_data>\n\n"
        f"<visitor_question>\n{message}\n</visitor_question>"
    )
    contents.append({"role": "user", "parts": [{"text": final_turn}]})
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,  # includes thinking tokens
            "thinkingConfig": {"thinkingLevel": "minimal"},
        },
    }
