"""Anonymous session tokens: standard JWTs (RFC 7519) signed with HMAC-SHA256 (HS256).

Implemented with the standard library so the Worker has no dependencies; unit tests cross-check
interoperability with PyJWT.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

ISSUER = "abinaya-chat-api"
AUDIENCE = "abinaya-chat-widget"
LEEWAY_SECONDS = 30
_HEADER = {"alg": "HS256", "typ": "JWT"}


class TokenError(Exception):
    """The token is missing, malformed, tampered with or invalid."""


class TokenExpired(TokenError):
    """The token was valid but has expired."""


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _sign(signing_input: bytes, key: str) -> str:
    return _b64encode(hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest())


def issue_token(key: str, ttl_seconds: int, now: float | None = None) -> tuple[str, dict[str, Any]]:
    issued_at = int(time.time() if now is None else now)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": f"s_{secrets.token_hex(8)}",  # anonymous session id (used for per-session limits)
        "jti": secrets.token_hex(8),
        "iat": issued_at,
        "exp": issued_at + ttl_seconds,
    }
    segments = [
        _b64encode(json.dumps(_HEADER, separators=(",", ":")).encode()),
        _b64encode(json.dumps(claims, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    return f"{segments[0]}.{segments[1]}.{_sign(signing_input, key)}", claims


def verify_token(token: str, key: str, now: float | None = None) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("malformed token")
    header_b64, payload_b64, signature = parts
    try:
        header = json.loads(_b64decode(header_b64))
    except ValueError as exc:
        raise TokenError("malformed header") from exc
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise TokenError("unsupported algorithm")  # blocks alg=none and algorithm confusion

    expected = _sign(f"{header_b64}.{payload_b64}".encode("ascii"), key)
    if not hmac.compare_digest(expected, signature):  # constant-time comparison
        raise TokenError("bad signature")

    try:
        claims = json.loads(_b64decode(payload_b64))
    except ValueError as exc:
        raise TokenError("malformed payload") from exc
    if not isinstance(claims, dict):
        raise TokenError("malformed payload")
    if claims.get("iss") != ISSUER or claims.get("aud") != AUDIENCE:
        raise TokenError("wrong issuer or audience")
    exp, iat = claims.get("exp"), claims.get("iat")
    if (
        not isinstance(exp, int)
        or not isinstance(iat, int)
        or not isinstance(claims.get("sub"), str)
    ):
        raise TokenError("missing claims")
    current = time.time() if now is None else now
    if iat > current + LEEWAY_SECONDS:
        raise TokenError("issued in the future")
    if current > exp + LEEWAY_SECONDS:
        raise TokenExpired("token expired")
    return claims
