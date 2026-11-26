"""Request dispatch, independent of the Cloudflare runtime.

`dispatch` turns (method, url, headers, env) into a JsonResult. It owns the top-level error
handling, so no exception ever leaks to the visitor as a stack trace. `main.py` is only a thin
adapter between Cloudflare's Request/Response objects and this function.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from config.settings import ConfigError, Settings
from core.context import RequestContext
from core.errors import ApiError, ErrorCode, error_result
from core.log import log_event
from core.responses import JsonResult
from routes import resolve


async def dispatch(
    method: str,
    url: str,
    headers: Mapping[str, str],
    env: Any,
    request_id: str,
) -> JsonResult:
    started = time.monotonic()
    path = urlsplit(url).path
    try:
        settings = Settings.from_env(env)
        handler = resolve(method, path)
        ctx = RequestContext(
            request_id=request_id,
            method=method.upper(),
            path=path,
            settings=settings,
            headers={k.lower(): v for k, v in headers.items()},
            env=env,
        )
        result = handler(ctx)
        if inspect.isawaitable(result):
            result = await result
    except ApiError as error:
        result = error_result(error, request_id)
    except ConfigError as error:
        log_event("error", "config_error", request_id=request_id, detail=str(error))
        result = error_result(ApiError(ErrorCode.INTERNAL_ERROR), request_id)
    except Exception as error:  # last-resort guard: never leak internals to clients
        log_event("error", "unhandled_exception", request_id=request_id, error=type(error).__name__)
        result = error_result(ApiError(ErrorCode.INTERNAL_ERROR), request_id)

    log_event(
        "info",
        "request",
        request_id=request_id,
        method=method.upper(),
        path=path,
        status=result.status,
        # Note: inside Workers the clock only advances during I/O, so this measures I/O wait.
        duration_ms=round((time.monotonic() - started) * 1000, 1),
    )
    return result
