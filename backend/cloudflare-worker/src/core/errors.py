"""API error codes and the error envelope from docs/api-contract.md.

Every non-streaming error has this shape:
    {"error": {"code": "...", "message": "..."}, "request_id": "r_..."}

Messages are deliberately generic: internal details belong in logs, never in responses.
"""

from __future__ import annotations

from enum import StrEnum

from core.responses import JsonResult


class ErrorCode(StrEnum):
    BAD_REQUEST = "bad_request"
    UNAUTHORIZED = "unauthorized"
    SESSION_EXPIRED = "session_expired"
    FORBIDDEN_ORIGIN = "forbidden_origin"
    TURNSTILE_FAILED = "turnstile_failed"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"


# code -> (HTTP status, default public message)
_ERROR_DETAILS: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.BAD_REQUEST: (400, "The request could not be processed."),
    ErrorCode.UNAUTHORIZED: (401, "Authentication is required."),
    ErrorCode.SESSION_EXPIRED: (401, "Your session has expired."),
    ErrorCode.FORBIDDEN_ORIGIN: (403, "This origin is not allowed."),
    ErrorCode.TURNSTILE_FAILED: (403, "Verification failed. Please try again."),
    ErrorCode.NOT_FOUND: (404, "The requested resource was not found."),
    ErrorCode.METHOD_NOT_ALLOWED: (405, "This method is not allowed for this resource."),
    ErrorCode.PAYLOAD_TOO_LARGE: (413, "The request body is too large."),
    ErrorCode.VALIDATION_ERROR: (422, "The request contains invalid data."),
    ErrorCode.RATE_LIMITED: (429, "Too many requests. Please slow down."),
    ErrorCode.INTERNAL_ERROR: (500, "Something went wrong. Please try again."),
    ErrorCode.UPSTREAM_UNAVAILABLE: (503, "The assistant is temporarily unavailable."),
}


def status_for(code: ErrorCode) -> int:
    return _ERROR_DETAILS[code][0]


class ApiError(Exception):
    """Raise anywhere in request handling to return a well-formed error response."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message or _ERROR_DETAILS[code][1]
        self.headers = headers or {}
        super().__init__(f"{code}: {self.message}")


def error_result(error: ApiError, request_id: str) -> JsonResult:
    return JsonResult(
        status=status_for(error.code),
        body={
            "error": {"code": str(error.code), "message": error.message},
            "request_id": request_id,
        },
        headers=dict(error.headers),
    )
