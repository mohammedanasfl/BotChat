"""Cloudflare Turnstile server-side verification (siteverify)."""

from __future__ import annotations

import secrets
from typing import Any

from config.settings import ConfigError
from services.http import request_json

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
EXPECTED_ACTION = "chat_session"
MAX_TOKEN_LENGTH = 2048
SECRET_ERRORS = {"missing-input-secret", "invalid-input-secret"}


def check_result(
    result: dict[str, Any], allowed_hostnames: tuple[str, ...], *, require_action: bool
) -> str | None:
    """Return None if the siteverify result is acceptable, otherwise a reason (for logs only).

    Raises ConfigError when Cloudflare reports a problem with *our* secret (a deployment bug).
    """
    codes = result.get("error-codes") or []
    if any(code in SECRET_ERRORS for code in codes):
        raise ConfigError(f"Turnstile secret rejected: {codes}")
    if not result.get("success"):
        return f"rejected: {result.get('error-codes')}"
    if result.get("hostname") not in allowed_hostnames:
        return f"hostname not allowed: {result.get('hostname')}"
    action = result.get("action")
    if action != EXPECTED_ACTION and (require_action or action is not None):
        return f"unexpected action: {action}"
    return None


async def siteverify(token: str, secret: str, remote_ip: str | None) -> dict[str, Any]:
    body = {
        "secret": secret,
        "response": token,
        # Same key on a retry returns the original result instead of failing as "already used".
        "idempotency_key": secrets.token_hex(16),
    }
    if remote_ip:
        body["remoteip"] = remote_ip
    # Siteverify answers rejected input with HTTP 400 + a JSON result: that is a verification
    # outcome, not an outage. Only 5xx / network errors raise (-> 503, fail closed).
    return await request_json(
        "turnstile",
        SITEVERIFY_URL,
        method="POST",
        body=body,
        timeout_ms=5000,
        accept_statuses=(400,),
    )
