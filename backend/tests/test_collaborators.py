"""Project collaborator visibility + permissions."""
from io import BytesIO
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.database import async_session
from app.models.project import Project, ProjectCollaborator
from app.models.task import Task


def _make_zip() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.py", "print('hi')\n")
    return buf.getvalue()


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    return r.json()["access_token"]


async def _admin(client: AsyncClient) -> str:
    return await _login(client, "admin", "admin123")


async def _make_user(
    client: AsyncClient, admin_token: str, username: str, role: str = "operator"
) -> str:
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.post(
        "/api/v1/users",
        headers=h,
        json={
            "username": username,
            "password": f"{username}-password",
            "role_codes": [role],
            "page_acls": ["projects", "tasks", "environments"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _make_project_as(
    client: AsyncClient, token: str, name: str
) -> str:
    body = {
        "name": name,
        "description": "",
        "source_type": "zip",
        "work_path": "/",
        "tags": [],
    }
    files = {
        "body": (None, __import__("json").dumps(body), "application/json"),
        "file": (f"{name}.zip", _make_zip(), "application/zip"),
    }
    r = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(autouse=True)
async def _clean_projects():
    """Slice B tests create projects across users — clear them between tests."""
    async with async_session() as s:
        await s.execute(delete(ProjectCollaborator))
        await s.execute(delete(Task))
        await s.execute(delete(Project))
        await s.commit()
    yield


@pytest.mark.asyncio
async def test_non_owner_cannot_see_project(client: AsyncClient):
    admin_t = await _admin(client)
    alice_id = await _make_user(client, admin_t, "alice")
    bob_id = await _make_user(client, admin_t, "bob")
    assert alice_id != bob_id

    alice_t = await _login(client, "alice", "alice-password")
    pid = await _make_project_as(client, alice_t, "alice-proj")

    bob_t = await _login(client, "bob", "bob-password")
    r = await client.get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {bob_t}"}
    )
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["items"]]
    assert "alice-proj" not in names

    r = await client.get(
        f"/api/v1/projects/{pid}",
        headers={"Authorization": f"Bearer {bob_t}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_collaborator_can_read_and_write(client: AsyncClient):
    admin_t = await _admin(client)
    await _make_user(client, admin_t, "alice")
    bob_id = await _make_user(client, admin_t, "bob")

    alice_t = await _login(client, "alice", "alice-password")
    pid = await _make_project_as(client, alice_t, "shared-proj")

    # Alice adds Bob as collaborator
    r = await client.post(
        f"/api/v1/projects/{pid}/collaborators",
        headers={"Authorization": f"Bearer {alice_t}"},
        json={"user_id": bob_id},
    )
    assert r.status_code == 201

    bob_t = await _login(client, "bob", "bob-password")

    # Bob can list and see the project
    r = await client.get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {bob_t}"}
    )
    names = [p["name"] for p in r.json()["items"]]
    assert "shared-proj" in names

    # Bob can update description
    r = await client.put(
        f"/api/v1/projects/{pid}",
        headers={"Authorization": f"Bearer {bob_t}"},
        json={"description": "edited by bob"},
    )
    assert r.status_code == 200, r.text

    # Bob cannot delete (only owner)
    r = await client.delete(
        f"/api/v1/projects/{pid}",
        headers={"Authorization": f"Bearer {bob_t}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_collaborator_listing(client: AsyncClient):
    admin_t = await _admin(client)
    await _make_user(client, admin_t, "alice")
    bob_id = await _make_user(client, admin_t, "bob")

    alice_t = await _login(client, "alice", "alice-password")
    pid = await _make_project_as(client, alice_t, "list-proj")

    await client.post(
        f"/api/v1/projects/{pid}/collaborators",
        headers={"Authorization": f"Bearer {alice_t}"},
        json={"user_id": bob_id},
    )

    r = await client.get(
        f"/api/v1/projects/{pid}/collaborators",
        headers={"Authorization": f"Bearer {alice_t}"},
    )
    assert r.status_code == 200
    usernames = [c["username"] for c in r.json()]
    assert "bob" in usernames

    # Remove
    r = await client.delete(
        f"/api/v1/projects/{pid}/collaborators/{bob_id}",
        headers={"Authorization": f"Bearer {alice_t}"},
    )
    assert r.status_code == 204

    bob_t = await _login(client, "bob", "bob-password")
    r = await client.get(
        f"/api/v1/projects/{pid}",
        headers={"Authorization": f"Bearer {bob_t}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_superuser_sees_all_projects(client: AsyncClient):
    admin_t = await _admin(client)
    await _make_user(client, admin_t, "alice")
    alice_t = await _login(client, "alice", "alice-password")
    await _make_project_as(client, alice_t, "alice-private")

    r = await client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {admin_t}"},
    )
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["items"]]
    assert "alice-private" in names


@pytest.mark.asyncio
async def test_only_owner_or_superuser_can_add_collaborator(client: AsyncClient):
    admin_t = await _admin(client)
    await _make_user(client, admin_t, "alice")
    bob_id = await _make_user(client, admin_t, "bob")
    await _make_user(client, admin_t, "carol")

    alice_t = await _login(client, "alice", "alice-password")
    pid = await _make_project_as(client, alice_t, "owner-controls")

    # Add bob as collab
    await client.post(
        f"/api/v1/projects/{pid}/collaborators",
        headers={"Authorization": f"Bearer {alice_t}"},
        json={"user_id": bob_id},
    )

    # Bob (collab) tries to add carol — should be forbidden
    bob_t = await _login(client, "bob", "bob-password")
    carol_id = (
        await client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_t}"},
        )
    ).json()["items"]
    carol_id = next(u["id"] for u in carol_id if u["username"] == "carol")

    r = await client.post(
        f"/api/v1/projects/{pid}/collaborators",
        headers={"Authorization": f"Bearer {bob_t}"},
        json={"user_id": carol_id},
    )
    assert r.status_code == 403
