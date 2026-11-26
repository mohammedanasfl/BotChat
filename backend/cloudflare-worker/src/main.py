"""Cloudflare Python Worker entry point.

This is the only module (besides future binding/HTTP adapters) that imports the `workers`
runtime. It converts Cloudflare's Request into plain values, calls the pure `dispatch`, and
converts the JsonResult back into a Cloudflare Response.
"""

from workers import Response, WorkerEntrypoint

from app import dispatch
from core.context import new_request_id
from core.responses import finalize_headers
from durable.rate_limiter import RateLimiter  # noqa: F401 - Durable Object class must be exported

# Reject oversized uploads from the header, before reading the body. Settings enforce the
# configured limit (MAX_BODY_BYTES, default 32 KB) on the body actually read.
HARD_BODY_LIMIT = 1_048_576


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        request_id = new_request_id()
        # Raw JS string: the SDK's `request.method` raises KeyError for non-standard methods.
        method = str(request.js_object.method)
        headers = {key: value for key, value in request.headers.items()}
        declared = headers.get("content-length") or headers.get("Content-Length") or "0"
        too_large = declared.isdigit() and int(declared) > _body_limit(self.env)
        reads_body = method in ("POST", "PUT", "PATCH") and not too_large
        body = await request.text() if reads_body else ""
        result = await dispatch(
            method, request.url, headers, self.env, request_id, body, body_too_large=too_large
        )
        return Response(
            result.encoded_body(),
            status=result.status,
            headers=finalize_headers(result, request_id),
        )


def _body_limit(env) -> int:
    value = str(getattr(env, "MAX_BODY_BYTES", "") or "")
    return min(int(value), HARD_BODY_LIMIT) if value.isdigit() else 32_768
