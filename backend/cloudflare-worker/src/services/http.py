"""The Worker's only outbound-HTTP adapter.

Runtime imports (`js`, `workers`) happen inside the function so this module (and everything that
imports it) stays importable under plain CPython for unit tests.
"""

from __future__ import annotations

import json
from typing import Any


class UpstreamError(Exception):
    """An upstream call failed, timed out or returned a non-2xx status."""

    def __init__(self, service: str, detail: str, status: int | None = None) -> None:
        self.service = service
        self.status = status
        super().__init__(f"{service}: {detail}")


async def request_json(
    service: str,
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout_ms: int = 8000,
    accept_statuses: tuple[int, ...] = (),
) -> dict[str, Any]:
    """POST/GET JSON. Non-2xx raises UpstreamError unless listed in accept_statuses."""
    from js import AbortSignal
    from workers import fetch

    options: dict[str, Any] = {
        "method": method,
        "headers": {"content-type": "application/json", **(headers or {})},
        "signal": AbortSignal.timeout(timeout_ms),
    }
    if body is not None:
        options["body"] = json.dumps(body)
    try:
        response = await fetch(url, **options)
    except Exception as exc:  # network error or timeout (AbortSignal)
        raise UpstreamError(service, f"request failed: {type(exc).__name__}") from exc
    if not 200 <= response.status < 300 and response.status not in accept_statuses:
        raise UpstreamError(service, f"HTTP {response.status}", status=response.status)
    try:
        return json.loads(await response.text())
    except ValueError as exc:
        raise UpstreamError(service, "invalid JSON response") from exc
