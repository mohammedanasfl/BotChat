"""Runtime-independent HTTP results.

Handlers return a `JsonResult` instead of a Cloudflare `Response`. Only `main.py` converts it,
so every handler can be unit-tested on plain CPython without the Workers runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

JSON_CONTENT_TYPE = "application/json; charset=utf-8"


@dataclass(frozen=True)
class JsonResult:
    status: int
    body: dict[str, Any] | None  # None = no body (e.g. 204 preflight)
    headers: dict[str, str] = field(default_factory=dict)

    def encoded_body(self) -> str | None:
        if self.body is None:
            return None
        return json.dumps(self.body, separators=(",", ":"), ensure_ascii=False)


def json_result(body: dict[str, Any], status: int = 200, **headers: str) -> JsonResult:
    return JsonResult(status=status, body=body, headers=dict(headers))


def finalize_headers(result: JsonResult, request_id: str) -> dict[str, str]:
    """Headers added to every API response."""
    headers = {
        "content-type": JSON_CONTENT_TYPE,
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
        "x-request-id": request_id,
    }
    headers.update({name.lower(): value for name, value in result.headers.items()})
    return headers
