"""GET /api/health: liveness. Says the Worker is running; never touches dependencies or secrets.

GET /api/health/ready (dependency checks) is added in Phase 4.
"""

from __future__ import annotations

from core.context import RequestContext
from core.responses import JsonResult, json_result


def health(ctx: RequestContext) -> JsonResult:
    return json_result({"status": "ok", "version": ctx.settings.version})
