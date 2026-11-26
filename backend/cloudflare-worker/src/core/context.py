"""Per-request context passed to every route handler."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config.settings import Settings


def new_request_id() -> str:
    # Must only be called inside request handling: Python Workers forbid randomness at module
    # import time (the module state is captured in a deploy-time memory snapshot).
    return f"r_{secrets.token_hex(6)}"


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    method: str
    path: str
    settings: Settings
    headers: dict[str, str] = field(default_factory=dict)  # lower-cased names
    body: str = ""
    env: Any = None  # raw bindings (Vectorize, rate limiter)
    abort_signal: Any = None  # JS AbortSignal that fires when the visitor disconnects

    def json(self) -> dict[str, Any]:
        from core.errors import ApiError, ErrorCode

        try:
            data = json.loads(self.body or "null")
        except ValueError as exc:
            raise ApiError(ErrorCode.BAD_REQUEST, "Request body must be valid JSON.") from exc
        if not isinstance(data, dict):
            raise ApiError(ErrorCode.BAD_REQUEST, "Request body must be a JSON object.")
        return data
