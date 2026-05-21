from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> Redis:
    return Redis(connection_pool=pool)
