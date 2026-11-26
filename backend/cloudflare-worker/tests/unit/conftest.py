from collections import Counter


class FakeRateLimiter:
    """Mimics the RATE_LIMITER Durable Object namespace: exact per-name counters."""

    def __init__(self):
        self.hits: Counter[str] = Counter()

    def getByName(self, name):
        limiter = self

        class Stub:
            async def hit(self, limit, period):
                limiter.hits[name] += 1
                return limiter.hits[name] <= limit

        return Stub()

    def keys(self, scope):
        return {name.split(":", 1)[1] for name in self.hits if name.startswith(f"{scope}:")}


def stub_gemini(monkeypatch, deltas=("Hi!",), finish="stop", fail_after=None, open_error=None):
    """Replace query embedding and the Gemini stream with fakes (no network)."""
    from services import embeddings, gemini_stream

    calls = {}

    async def fake_embed(text, key):
        calls["query"] = text
        return [0.1] * 768

    async def fake_open(request, *, model, api_key, abort_signal):
        if open_error:
            raise open_error
        calls["request"], calls["model"] = request, model
        return object()

    async def fake_iter(response, state):
        for i, text in enumerate(deltas):
            if fail_after is not None and i == fail_after:
                raise RuntimeError("upstream broke")
            state.emitted_text = True
            yield text
        state.finish_reason = finish
        state.usage = {"promptTokenCount": 10, "candidatesTokenCount": len(deltas)}

    monkeypatch.setattr(embeddings, "embed_query", fake_embed)
    monkeypatch.setattr(gemini_stream, "open_stream", fake_open)
    monkeypatch.setattr(gemini_stream, "iter_deltas", fake_iter)
    return calls


def collect(result):
    """Drain a StreamResult into a list of (event, data) tuples."""
    import asyncio
    import json

    async def drain():
        return [text async for text in result.events]

    events = []
    for block in asyncio.run(drain()):
        name, data = block.strip().split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events
