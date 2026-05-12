"""StockAI v2 — Rate Limiter

Token bucket rate limiter.
Phase 1: in-memory. Phase 3+: Redis-backed.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request


class TokenBucket:
    """Simple in-memory token bucket rate limiter."""

    def __init__(self, rate: int, per: int = 60):
        self.rate = rate  # max tokens
        self.per = per  # seconds
        self.tokens: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.per

        # Clean old entries
        self.tokens[key] = [t for t in self.tokens[key] if t > window_start]

        # Check rate
        if len(self.tokens[key]) >= self.rate:
            return False

        self.tokens[key].append(now)
        return True


# Rate limiters for different endpoints
auth_limiter = TokenBucket(rate=5, per=60)  # 5 auth requests per minute
stock_limiter = TokenBucket(rate=60, per=60)  # 60 stock requests per minute


def rate_limit(limiter: TokenBucket) -> Callable:
    """FastAPI dependency for rate limiting."""

    async def dependency(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        if not limiter.check(client_ip):
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                },
            )
        return True

    return dependency
