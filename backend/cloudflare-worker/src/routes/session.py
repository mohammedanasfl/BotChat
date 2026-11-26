"""POST /api/session: exchange a Turnstile token for a short-lived session token."""

from __future__ import annotations

from datetime import UTC, datetime

from config.settings import require_secret
from core.context import RequestContext
from core.errors import ApiError, ErrorCode
from core.log import log_event
from core.rate_limit import client_ip, enforce
from core.responses import JsonResult, json_result
from services.tokens import issue_token
from services.turnstile import MAX_TOKEN_LENGTH, check_result, siteverify


async def create_session(ctx: RequestContext) -> JsonResult:
    # Before any Turnstile call.
    await enforce(ctx.env.RATE_LIMITER, "session-ip", client_ip(ctx), ctx.settings.rate_session_ip)
    token = ctx.json().get("turnstile_token")
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "'turnstile_token' is required.")

    settings = ctx.settings
    secret = require_secret(settings.turnstile_secret_key, "TURNSTILE_SECRET_KEY")
    signing_key = require_secret(settings.session_signing_key, "SESSION_SIGNING_KEY")

    # Fails closed: if siteverify is unreachable, UpstreamError -> 503, never a free session.
    result = await siteverify(token, secret, ctx.headers.get("cf-connecting-ip"))
    reason = check_result(
        result, settings.turnstile_allowed_hostnames, require_action=settings.is_production
    )
    if reason:
        log_event("warning", "turnstile_failed", request_id=ctx.request_id, reason=reason)
        raise ApiError(ErrorCode.TURNSTILE_FAILED)

    session_token, claims = issue_token(signing_key, settings.session_ttl_seconds)
    log_event("info", "session_created", request_id=ctx.request_id, session=claims["sub"])
    return json_result(
        {
            "session_token": session_token,
            "token_type": "Bearer",
            "expires_in": settings.session_ttl_seconds,
            "expires_at": datetime.fromtimestamp(claims["exp"], UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
