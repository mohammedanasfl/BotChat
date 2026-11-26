"""Route table and resolution (pure; no runtime imports).

Routes map an exact path to {HTTP method: handler}. A handler takes a RequestContext and returns
a JsonResult (or an awaitable of one).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.context import RequestContext
from core.errors import ApiError, ErrorCode
from core.responses import JsonResult
from routes.dev import dev_answer
from routes.health import health, ready

Handler = Callable[[RequestContext], JsonResult | Awaitable[JsonResult]]

ROUTES: dict[str, dict[str, Handler]] = {
    "/api/health": {"GET": health},
    "/api/health/ready": {"GET": ready},
    "/api/dev/answer": {"POST": dev_answer},  # development only (404 in production)
}


def normalize_path(path: str) -> str:
    if len(path) > 1 and path.endswith("/"):
        return path.rstrip("/") or "/"
    return path or "/"


def resolve(method: str, path: str) -> Handler:
    methods = ROUTES.get(normalize_path(path))
    if methods is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    handler = methods.get(method.upper())
    if handler is None:
        raise ApiError(ErrorCode.METHOD_NOT_ALLOWED, headers={"allow": ", ".join(sorted(methods))})
    return handler
