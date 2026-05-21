"""Redis-backed sliding-window rate limiter.

Used by sensitive endpoints like /auth/login to thwart brute-force attempts.
"""
from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.redis import get_redis


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded; retry after {retry_after}s")


async def check_and_incr(key: str, limit: int, window_seconds: int) -> None:
    """Check if `key` is within `limit` hits per `window_seconds`. Increment counter.

    Raises RateLimitExceeded(retry_after) if over limit.
    Uses fixed window (counter expires after window). Simpler and good enough
    for login brute-force protection.
    """
    redis = await get_redis()
    try:
        # INCR + EXPIRE in a pipeline for atomicity-ish.
        async with redis.pipeline(transaction=True) as p:
            p.incr(key)
            p.ttl(key)
            results = await p.execute()
        count, ttl = int(results[0]), int(results[1])
        if ttl < 0:
            await redis.expire(key, window_seconds)
            ttl = window_seconds
        if count > limit:
            raise RateLimitExceeded(retry_after=max(ttl, 1))
    finally:
        await redis.aclose()


async def reset(key: str) -> None:
    """Clear counter (call on successful auth)."""
    redis = await get_redis()
    try:
        await redis.delete(key)
    finally:
        await redis.aclose()


def api_rate_limit(name: str, limit: int, window: int):
    """FastAPI dependency factory: per-IP rate limit on an endpoint.

    Usage:
        @router.post("...", dependencies=[Depends(api_rate_limit("project_write", 60, 60))])

    Returns a callable that raises HTTPException(429) when over limit.
    """

    async def _dep(request: Request):
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        key = f"rl:api:{name}:{client_ip}"
        try:
            await check_and_incr(key, limit, window)
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请 {exc.retry_after} 秒后再试",
                headers={"Retry-After": str(exc.retry_after)},
            )

    return _dep
