"""CORS with an exact-origin allowlist.

Origin checks are defense in depth, not authentication: non-browser clients can send any Origin.
Requests without an Origin header (curl, uptime checks) are allowed through; Turnstile and session
tokens (Phase 6) are the real gate.
"""

from __future__ import annotations

from core.errors import ApiError, ErrorCode
from core.responses import JsonResult

ALLOWED_METHODS = "GET, POST, OPTIONS"
ALLOWED_HEADERS = "Authorization, Content-Type"
EXPOSED_HEADERS = "X-Request-Id, Retry-After"
PREFLIGHT_MAX_AGE = "600"


def check_origin(origin: str | None, allowed: tuple[str, ...]) -> None:
    if origin is not None and origin not in allowed:
        raise ApiError(ErrorCode.FORBIDDEN_ORIGIN)


def cors_headers(origin: str | None, allowed: tuple[str, ...]) -> dict[str, str]:
    if origin is None or origin not in allowed:
        return {}
    return {
        "access-control-allow-origin": origin,
        "access-control-expose-headers": EXPOSED_HEADERS,
        "vary": "Origin",
    }


def preflight() -> JsonResult:
    return JsonResult(
        status=204,
        body=None,
        headers={
            "access-control-allow-methods": ALLOWED_METHODS,
            "access-control-allow-headers": ALLOWED_HEADERS,
            "access-control-max-age": PREFLIGHT_MAX_AGE,
        },
    )
