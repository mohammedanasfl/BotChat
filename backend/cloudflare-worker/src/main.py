"""Cloudflare Python Worker entry point.

This is the only module (besides future binding/HTTP adapters) that imports the `workers`
runtime. It converts Cloudflare's Request into plain values, calls the pure `dispatch`, and
converts the JsonResult back into a Cloudflare Response.
"""

from workers import Response, WorkerEntrypoint

from app import dispatch
from core.context import new_request_id
from core.log import log_event
from core.responses import finalize_headers
from core.sse import StreamResult
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
            method,
            request.url,
            headers,
            self.env,
            request_id,
            body,
            body_too_large=too_large,
            abort_signal=request.js_object.signal,
        )
        if isinstance(result, StreamResult):
            return _stream_response(result, request_id)
        return Response(
            result.encoded_body(),
            status=result.status,
            headers=finalize_headers(result, request_id),
        )


def _body_limit(env) -> int:
    value = str(getattr(env, "MAX_BODY_BYTES", "") or "")
    return min(int(value), HARD_BODY_LIMIT) if value.isdigit() else 32_768


def _stream_response(result: StreamResult, request_id: str):
    """Return the readable side of a TransformStream now; write SSE events in the background."""
    import asyncio

    from js import Response as JsResponse
    from js import TextEncoder, TransformStream
    from pyodide.ffi import create_proxy, to_js
    from workers import wait_until

    stream = TransformStream.new()
    writer = stream.writable.getWriter()

    async def pump() -> None:
        encoder = TextEncoder.new()
        try:
            async for text in result.events:
                await writer.write(encoder.encode(text))  # rejects if the visitor disconnected
        except Exception as error:
            log_event("info", "stream_closed", request_id=request_id, reason=type(error).__name__)
        finally:
            await result.events.aclose()
            try:
                writer.close()  # not awaited: settles only once a reader drains the stream
            except Exception:  # noqa: S110 - stream already closed by the client
                pass

    task = asyncio.ensure_future(pump())
    proxy = create_proxy(task)
    task.add_done_callback(lambda _done: proxy.destroy())
    wait_until(proxy)  # keep the Worker alive until the stream is fully written

    headers = finalize_headers(result, request_id)
    return JsResponse.new(stream.readable, status=result.status, headers=to_js(headers))
