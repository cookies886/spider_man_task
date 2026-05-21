"""Brute-force protection on /auth/login."""
import pytest
from httpx import AsyncClient

from app.core.redis import get_redis


@pytest.fixture(autouse=True)
async def _clear_rate_limit_keys():
    """Wipe any leftover rate-limit keys from prior tests."""
    redis = await get_redis()
    try:
        async for key in redis.scan_iter(match="rl:login:*"):
            await redis.delete(key)
    finally:
        await redis.aclose()
    yield


@pytest.mark.asyncio
async def test_login_5_wrong_then_429(client: AsyncClient):
    body = {"username": "admin", "password": "definitely-wrong"}
    # First 5 are 401
    for i in range(5):
        r = await client.post("/api/v1/auth/login", json=body)
        assert r.status_code == 401, f"attempt {i + 1} unexpected: {r.text}"
    # 6th is 429
    r = await client.post("/api/v1/auth/login", json=body)
    assert r.status_code == 429, r.text
    assert "Retry-After" in r.headers
    body_json = r.json()
    assert "频繁" in body_json["detail"]


@pytest.mark.asyncio
async def test_correct_password_resets_counter(client: AsyncClient):
    bad = {"username": "admin", "password": "wrong"}
    # 4 wrong attempts (still under threshold)
    for _ in range(4):
        r = await client.post("/api/v1/auth/login", json=bad)
        assert r.status_code == 401
    # Correct password — should succeed AND clear counter
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200
    # Now 5 more wrong attempts should still be allowed (counter was reset)
    for i in range(5):
        r = await client.post("/api/v1/auth/login", json=bad)
        assert r.status_code == 401, f"after-reset attempt {i + 1}: {r.text}"
