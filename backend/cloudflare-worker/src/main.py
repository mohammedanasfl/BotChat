"""Cloudflare Python Worker entry point.

This is the only module (besides future binding/HTTP adapters) that imports the `workers`
runtime. It converts Cloudflare's Request into plain values, calls the pure `dispatch`, and
converts the JsonResult back into a Cloudflare Response.
"""

from workers import Response, WorkerEntrypoint

from app import dispatch
from core.context import new_request_id
from core.responses import finalize_headers


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        request_id = new_request_id()
        # Raw JS string: the SDK's `request.method` raises KeyError for non-standard methods.
        method = str(request.js_object.method)
        headers = {key: value for key, value in request.headers.items()}
        body = await request.text() if method in ("POST", "PUT", "PATCH") else ""
        result = await dispatch(method, request.url, headers, self.env, request_id, body)
        return Response(
            result.encoded_body(),
            status=result.status,
            headers=finalize_headers(result, request_id),
        )
