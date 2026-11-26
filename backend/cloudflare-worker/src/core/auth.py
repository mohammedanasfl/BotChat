"""Session authentication for protected routes."""

from __future__ import annotations

from typing import Any

from config.settings import require_secret
from core.context import RequestContext
from core.errors import ApiError, ErrorCode
from services.tokens import TokenError, TokenExpired, verify_token


def require_session(ctx: RequestContext) -> dict[str, Any]:
    """Return the verified session claims or raise 401."""
    header = ctx.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(ErrorCode.UNAUTHORIZED)
    key = require_secret(ctx.settings.session_signing_key, "SESSION_SIGNING_KEY")
    try:
        return verify_token(token.strip(), key)
    except TokenExpired as exc:
        raise ApiError(ErrorCode.SESSION_EXPIRED) from exc
    except TokenError as exc:
        raise ApiError(ErrorCode.UNAUTHORIZED) from exc
