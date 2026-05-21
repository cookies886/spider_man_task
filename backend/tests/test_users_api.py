import pytest
from httpx import AsyncClient


async def _admin_token(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_creates_viewer_user(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/users",
        headers=h,
        json={
            "username": "viewer1",
            "password": "viewer1password",
            "role_codes": ["viewer"],
            "page_acls": ["dashboard"],
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["username"] == "viewer1"
    assert data["role_codes"] == ["viewer"]
    assert data["page_acls"] == ["dashboard"]


@pytest.mark.asyncio
async def test_viewer_cannot_list_users(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/users",
        headers=h,
        json={
            "username": "viewer2",
            "password": "viewer2password",
            "role_codes": ["viewer"],
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "viewer2", "password": "viewer2password"},
    )
    vt = r.json()["access_token"]
    r = await client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {vt}"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_roles(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    r = await client.get("/api/v1/roles", headers=h)
    assert r.status_code == 200
    codes = {r["code"] for r in r.json()}
    assert {"admin", "operator", "viewer"} <= codes


@pytest.mark.asyncio
async def test_cannot_delete_superuser(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    r = await client.get("/api/v1/users", headers=h)
    admin = next(u for u in r.json()["items"] if u["username"] == "admin")
    r = await client.delete(f"/api/v1/users/{admin['id']}", headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_viewer_cannot_create_worker(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/users",
        headers=h,
        json={
            "username": "viewer3",
            "password": "viewer3password",
            "role_codes": ["viewer"],
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "viewer3", "password": "viewer3password"},
    )
    vt = r.json()["access_token"]
    r = await client.post(
        "/api/v1/workers",
        headers={"Authorization": f"Bearer {vt}"},
        json={"name": "x", "hostname": "x", "ip": "1.1.1.1"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_operator_can_read_workers_but_not_create(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/users",
        headers=h,
        json={
            "username": "op1",
            "password": "op1password",
            "role_codes": ["operator"],
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "op1", "password": "op1password"},
    )
    ot = r.json()["access_token"]
    r = await client.get(
        "/api/v1/workers", headers={"Authorization": f"Bearer {ot}"}
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/workers",
        headers={"Authorization": f"Bearer {ot}"},
        json={"name": "x", "hostname": "x", "ip": "1.1.1.1"},
    )
    assert r.status_code == 403
