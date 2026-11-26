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
