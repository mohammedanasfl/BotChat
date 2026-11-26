"""RateLimiter Durable Object: one instance per limiter key (e.g. "chat-ip:<ip>").

Cloudflare guarantees a single instance per name, so its counter is exact. The counting logic is
the pure `count_hit` function in core.rate_limit; this class only persists the state.
"""

import time

from workers import DurableObject

from core.rate_limit import count_hit


class RateLimiter(DurableObject):
    async def hit(self, limit: int, period: int) -> bool:
        stored = await self.ctx.storage.get("window")
        state, count = count_hit(stored, time.time(), period)
        await self.ctx.storage.put("window", state)
        return count <= limit
