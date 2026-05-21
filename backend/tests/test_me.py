import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_me_returns_admin_info(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "admin"
    assert body["is_superuser"] is True
    assert "task.execute" in body["permissions"]
    assert "dashboard" in body["page_acls"]


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/me/change-password",
        headers=h,
        json={"old_password": "admin123", "new_password": "newadminpw1"},
    )
    assert r.status_code == 204

    # old password fails
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert r.status_code == 401
    # new password works
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "newadminpw1"}
    )
    assert r.status_code == 200

    # restore so other tests still work
    token2 = r.json()["access_token"]
    await client.post(
        "/api/v1/me/change-password",
        headers={"Authorization": f"Bearer {token2}"},
        json={"old_password": "newadminpw1", "new_password": "admin123"},
    )
