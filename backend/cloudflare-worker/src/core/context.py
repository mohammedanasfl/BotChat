"""Per-request context passed to every route handler."""

from __future__ import annotations

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
    env: Any = None  # raw bindings (secrets, Vectorize, rate limiters) for later phases
