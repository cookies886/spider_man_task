import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import async_session, engine
from app.core import redis as redis_module
from app.core.seed import ensure_seed_data
from app.main import app
from app.models.user import User
from app.models.worker import Worker, WorkerGroup


@pytest_asyncio.fixture(autouse=True)
async def _isolate_async_engine():
    """Each test gets a clean engine so asyncpg doesn't carry connections
    across pytest-asyncio's per-test event loops. Also drops mutable rows
    left behind by prior test runs so create-uniqueness tests stay green."""
    # Wipe rate-limit counters from earlier tests so login throttle doesn't
    # bleed between cases.
    from app.core.redis import get_redis as _get_redis
    _r = await _get_redis()
    try:
        async for _k in _r.scan_iter(match="rl:*"):
            await _r.delete(_k)
    finally:
        await _r.aclose()

    async with async_session() as s:
        await s.execute(delete(User).where(User.is_superuser.is_(False)))
        await s.execute(delete(Worker).where(Worker.node_id != "master-local"))
        await s.execute(delete(WorkerGroup))
        await s.commit()
    yield
    await engine.dispose()
    # Same problem applies to the redis pool: connections bind to the test's
    # event loop, and pytest-asyncio gives each test a fresh loop. Recreate
    # the pool after each test so the next one starts clean.
    from redis.asyncio import ConnectionPool
    from app.core.config import settings as _settings
    try:
        await redis_module.pool.aclose()
    except Exception:
        pass
    redis_module.pool = ConnectionPool.from_url(
        _settings.redis_url, decode_responses=True
    )


@pytest_asyncio.fixture
async def client():
    await ensure_seed_data()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
