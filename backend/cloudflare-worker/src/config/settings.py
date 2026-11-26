"""Typed configuration read from Worker bindings (`self.env`).

All configuration is parsed and validated here, in one place, so a missing or malformed value
fails loudly and early instead of surfacing deep inside a request.

`env` is duck-typed: in the Worker it is the JS env proxy; in tests any object with attributes
(e.g. `types.SimpleNamespace`) works. Secrets are added to this class in the phases that use them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

APP_VERSION = "0.1.0"

ENVIRONMENTS = frozenset({"development", "production"})


class ConfigError(ValueError):
    """Worker configuration is missing or invalid (a deployment bug, not a client error)."""


@dataclass(frozen=True)
class Settings:
    environment: str
    allowed_origins: tuple[str, ...]
    max_body_bytes: int
    max_message_chars: int
    max_history_messages: int
    session_ttl_seconds: int
    gemini_model: str
    gemini_max_output_tokens: int
    search_top_k: int
    search_min_score: float
    gemini_api_key: str = field(default="", repr=False)  # secret: never logged
    version: str = APP_VERSION

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls, env: Any) -> Settings:
        environment = _read_str(env, "ENVIRONMENT", default="production")
        if environment not in ENVIRONMENTS:
            raise ConfigError(f"ENVIRONMENT must be one of {sorted(ENVIRONMENTS)}")

        settings = cls(
            environment=environment,
            allowed_origins=_parse_origins(_read_str(env, "ALLOWED_ORIGINS", default="")),
            max_body_bytes=_read_int(
                env, "MAX_BODY_BYTES", 32_768, minimum=1_024, maximum=1_048_576
            ),
            max_message_chars=_read_int(env, "MAX_MESSAGE_CHARS", 1_000, minimum=1, maximum=10_000),
            max_history_messages=_read_int(env, "MAX_HISTORY_MESSAGES", 10, minimum=0, maximum=50),
            session_ttl_seconds=_read_int(
                env, "SESSION_TTL_SECONDS", 900, minimum=60, maximum=3_600
            ),
            gemini_model=_read_str(env, "GEMINI_MODEL", default="gemini-3.5-flash-lite"),
            gemini_max_output_tokens=_read_int(
                env, "GEMINI_MAX_OUTPUT_TOKENS", 1_024, minimum=64, maximum=8_192
            ),
            search_top_k=_read_int(env, "SEARCH_TOP_K", 4, minimum=1, maximum=10),
            search_min_score=_read_float(env, "SEARCH_MIN_SCORE", 0.60),
            gemini_api_key=_read_str(env, "GEMINI_API_KEY", default=""),
        )
        settings._validate()
        return settings

    def _validate(self) -> None:
        if self.is_production:
            if not self.allowed_origins:
                raise ConfigError("ALLOWED_ORIGINS must not be empty in production")
            insecure = [o for o in self.allowed_origins if not o.startswith("https://")]
            if insecure:
                raise ConfigError(f"Production origins must use https: {insecure}")


def _raw(env: Any, name: str) -> Any:
    # Unknown names: JS env proxies raise AttributeError (or yield None for `undefined`).
    return getattr(env, name, None)


def _read_str(env: Any, name: str, *, default: str) -> str:
    value = _raw(env, name)
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _read_int(env: Any, name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = _raw(env, name)
    if value is None or str(value).strip() == "":
        number = default
    else:
        try:
            number = int(str(value).strip())
        except ValueError as exc:
            raise ConfigError(f"{name} must be an integer") from exc
    if not minimum <= number <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return number


def _read_float(env: Any, name: str, default: float) -> float:
    value = _raw(env, name)
    if value is None or str(value).strip() == "":
        return default
    try:
        number = float(str(value).strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not 0.0 <= number <= 1.0:
        raise ConfigError(f"{name} must be between 0 and 1")
    return number


def require_gemini_key(settings: Settings) -> str:
    if not settings.gemini_api_key:
        raise ConfigError("GEMINI_API_KEY secret is not set")
    return settings.gemini_api_key


def _parse_origins(raw: str) -> tuple[str, ...]:
    """Parse a comma-separated origin list into normalized exact origins (scheme://host[:port])."""
    origins: list[str] = []
    for item in raw.split(","):
        candidate = item.strip().rstrip("/")
        if not candidate:
            continue
        if "*" in candidate:
            raise ConfigError("Wildcard origins are not allowed")
        parts = urlsplit(candidate)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ConfigError(f"Invalid origin: {candidate!r}")
        if parts.path or parts.query or parts.fragment:
            raise ConfigError(f"Origin must not contain a path, query or fragment: {candidate!r}")
        origins.append(f"{parts.scheme}://{parts.netloc.lower()}")
    return tuple(dict.fromkeys(origins))  # de-duplicate, keep order
