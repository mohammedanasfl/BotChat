"""Split the model's follow-up questions off the streamed answer.

The model ends its answer with FOLLOW_UPS_MARKER and one question per line. The visitor must
never see the marker, so text that could be the start of it is held back until it is ruled out.
"""

from __future__ import annotations

FOLLOW_UPS_MARKER = "<<FOLLOW_UPS>>"
MAX_FOLLOW_UPS = 3
MAX_FOLLOW_UP_CHARS = 120


class FollowUpSplitter:
    def __init__(self) -> None:
        self._pending = ""  # answer text not yet released
        self._tail: str | None = None  # text after the marker, once it has been seen

    def feed(self, text: str) -> str:
        """Return the answer text that is safe to show now."""
        if self._tail is not None:
            self._tail += text
            return ""
        self._pending += text
        index = self._pending.find(FOLLOW_UPS_MARKER)
        if index != -1:
            self._tail = self._pending[index + len(FOLLOW_UPS_MARKER) :]
            visible, self._pending = self._pending[:index].rstrip(), ""
            return visible
        hold = _partial_marker_length(self._pending)
        cut = len(self._pending) - hold
        while cut and self._pending[cut - 1].isspace():  # don't leave a blank line before it
            cut -= 1
        visible, self._pending = self._pending[:cut], self._pending[cut:]
        return visible

    def finish(self) -> tuple[str, list[str]]:
        """Return (remaining answer text, follow-up questions) once the stream has ended."""
        visible, self._pending = self._pending, ""
        return visible, parse_follow_ups(self._tail or "")


def _partial_marker_length(text: str) -> int:
    """Length of the longest end of `text` that is a start of the marker."""
    for size in range(min(len(text), len(FOLLOW_UPS_MARKER) - 1), 0, -1):
        if FOLLOW_UPS_MARKER.startswith(text[-size:]):
            return size
    return 0


def parse_follow_ups(text: str) -> list[str]:
    questions: list[str] = []
    for line in text.splitlines():
        question = line.strip().lstrip("-*•0123456789.) ").strip()
        if question and len(question) <= MAX_FOLLOW_UP_CHARS and question not in questions:
            questions.append(question)
    return questions[:MAX_FOLLOW_UPS]
