import pytest
from httpx import AsyncClient


async def _admin_token(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_create_list_update_delete_group(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/worker-groups",
        headers=h,
        json={"name": "win-cluster", "description": "windows boxes", "tags": ["win"]},
    )
    assert r.status_code == 201
    gid = r.json()["id"]
    assert r.json()["worker_count"] == 0

    r = await client.get("/api/v1/worker-groups", headers=h)
    assert r.status_code == 200
    names = [g["name"] for g in r.json()]
    assert "win-cluster" in names

    r = await client.patch(
        f"/api/v1/worker-groups/{gid}",
        headers=h,
        json={"description": "updated"},
    )
    assert r.status_code == 200
    assert r.json()["description"] == "updated"

    r = await client.delete(f"/api/v1/worker-groups/{gid}", headers=h)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_duplicate_group_name_409(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    r = await client.post(
        "/api/v1/worker-groups", headers=h, json={"name": "linux-pool"}
    )
    assert r.status_code == 201
    r = await client.post(
        "/api/v1/worker-groups", headers=h, json={"name": "linux-pool"}
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_worker_with_group_id(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/worker-groups", headers=h, json={"name": "edit-grp"}
    )
    gid = r.json()["id"]

    r = await client.post(
        "/api/v1/workers",
        headers=h,
        json={
            "name": "g-worker",
            "hostname": "host",
            "ip": "10.0.0.1",
            "type": "remote",
            "group_id": gid,
        },
    )
    assert r.status_code == 201
    wid = r.json()["id"]
    assert r.json()["group_id"] == gid

    r = await client.get("/api/v1/worker-groups", headers=h)
    grp = next(g for g in r.json() if g["id"] == gid)
    assert grp["worker_count"] == 1

    r = await client.patch(
        f"/api/v1/workers/{wid}", headers=h, json={"group_id": None, "max_slots": 8}
    )
    assert r.status_code == 200
    assert r.json()["group_id"] is None
    assert r.json()["max_slots"] == 8


@pytest.mark.asyncio
async def test_viewer_cannot_create_group(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/users",
        headers=h,
        json={
            "username": "viewer-grp",
            "password": "viewer-grp-password",
            "role_codes": ["viewer"],
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "viewer-grp", "password": "viewer-grp-password"},
    )
    vt = r.json()["access_token"]
    vh = {"Authorization": f"Bearer {vt}"}

    r = await client.get("/api/v1/worker-groups", headers=vh)
    assert r.status_code == 200

    r = await client.post(
        "/api/v1/worker-groups", headers=vh, json={"name": "no-can-do"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_worker_with_invalid_group_400(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    r = await client.post(
        "/api/v1/workers",
        headers=h,
        json={
            "name": "bad",
            "hostname": "h",
            "ip": "1.1.1.1",
            "type": "remote",
            "group_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert r.status_code == 400
