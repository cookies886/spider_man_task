"""GET /tasks/runs/{run_id}/logs filtering."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.database import async_session
from app.models.project import Project, ProjectCollaborator
from app.models.task import RunStatus, Task, TaskRun


def _make_zip() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.py", "print('hi')\n")
    return buf.getvalue()


async def _admin_token(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    return r.json()["access_token"]


async def _create_project(client: AsyncClient, token: str, name: str) -> str:
    body = {
        "name": name,
        "description": "",
        "source_type": "zip",
        "work_path": "/",
        "tags": [],
    }
    files = {
        "body": (None, json.dumps(body), "application/json"),
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
async def _clean():
    async with async_session() as s:
        await s.execute(delete(ProjectCollaborator))
        await s.execute(delete(TaskRun))
        await s.execute(delete(Task))
        await s.execute(delete(Project))
        await s.commit()
    yield


def _write_jsonl(path: str, lines: list[dict]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in lines:
            fh.write(json.dumps(r) + "\n")


@pytest.mark.asyncio
async def test_logs_endpoint_level_filter(client: AsyncClient, tmp_path):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}

    pid = await _create_project(client, token, "log-filter-proj")
    # Manually craft a Task + TaskRun + JSONL file
    run_id = uuid.uuid4()
    log_path = str(tmp_path / "run.log")
    _write_jsonl(
        log_path,
        [
            {"ts": "2026-05-18T10:00:00+00:00", "stream": "stdout", "line": "hello"},
            {"ts": "2026-05-18T10:00:01+00:00", "stream": "stderr", "line": "boom"},
            {"ts": "2026-05-18T10:00:02+00:00", "stream": "stdout", "line": "another"},
        ],
    )
    async with async_session() as s:
        t = Task(
            name="log-filter-task",
            project_id=pid,
            command="echo hi",
            schedule_type="cron",
            schedule_config={"cron": "0 0 * * *"},
            node_strategy="auto",
        )
        s.add(t)
        await s.flush()
        r = TaskRun(
            id=run_id,
            task_id=t.id,
            status=RunStatus.SUCCESS,
            log_file_path=log_path,
            started_at=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 5, 18, 10, 1, tzinfo=timezone.utc),
        )
        s.add(r)
        await s.commit()

    # All
    rsp = await client.get(f"/api/v1/tasks/runs/{run_id}/logs", headers=h)
    assert rsp.status_code == 200, rsp.text
    body = rsp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3

    # ERROR only -> stderr line
    rsp = await client.get(
        f"/api/v1/tasks/runs/{run_id}/logs", headers=h, params={"level": "ERROR"}
    )
    assert rsp.status_code == 200
    body = rsp.json()
    assert body["total"] == 1
    assert body["items"][0]["line"] == "boom"
    assert body["items"][0]["level"] == "ERROR"

    # keyword
    rsp = await client.get(
        f"/api/v1/tasks/runs/{run_id}/logs", headers=h, params={"keyword": "hello"}
    )
    assert rsp.json()["total"] == 1
    assert rsp.json()["items"][0]["line"] == "hello"

    # time range — exclude after 10:00:01
    rsp = await client.get(
        f"/api/v1/tasks/runs/{run_id}/logs",
        headers=h,
        params={"until": "2026-05-18T10:00:01+00:00"},
    )
    assert rsp.json()["total"] == 2

    # pagination
    rsp = await client.get(
        f"/api/v1/tasks/runs/{run_id}/logs",
        headers=h,
        params={"offset": 1, "limit": 1},
    )
    body = rsp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["items"][0]["line"] == "boom"


@pytest.mark.asyncio
async def test_logs_endpoint_returns_empty_when_no_file(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    pid = await _create_project(client, token, "nolog-proj")

    run_id = uuid.uuid4()
    async with async_session() as s:
        t = Task(
            name="no-log-task",
            project_id=pid,
            command="echo",
            schedule_type="cron",
            schedule_config={"cron": "0 0 * * *"},
            node_strategy="auto",
        )
        s.add(t)
        await s.flush()
        s.add(TaskRun(id=run_id, task_id=t.id, status=RunStatus.PENDING))
        await s.commit()

    rsp = await client.get(f"/api/v1/tasks/runs/{run_id}/logs", headers=h)
    assert rsp.status_code == 200
    assert rsp.json() == {"items": [], "total": 0, "offset": 0, "limit": 1000}


@pytest.mark.asyncio
async def test_logs_endpoint_404_when_run_missing(client: AsyncClient):
    token = await _admin_token(client)
    h = {"Authorization": f"Bearer {token}"}
    rsp = await client.get(
        f"/api/v1/tasks/runs/{uuid.uuid4()}/logs", headers=h
    )
    assert rsp.status_code == 404


@pytest.mark.asyncio
async def test_logs_endpoint_blocks_non_collaborator(client: AsyncClient, tmp_path):
    admin_t = await _admin_token(client)
    h = {"Authorization": f"Bearer {admin_t}"}

    # Create alice user
    await client.post(
        "/api/v1/users",
        headers=h,
        json={
            "username": "alice2",
            "password": "alice2-password",
            "role_codes": ["operator"],
            "page_acls": ["projects", "tasks"],
        },
    )
    alice_t = (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "alice2", "password": "alice2-password"},
        )
    ).json()["access_token"]

    # Create project as admin
    pid = await _create_project(client, admin_t, "private-proj")

    run_id = uuid.uuid4()
    log_path = str(tmp_path / "private.log")
    _write_jsonl(log_path, [{"ts": "x", "stream": "stdout", "line": "x"}])
    async with async_session() as s:
        t = Task(
            name="private-task",
            project_id=pid,
            command="echo",
            schedule_type="cron",
            schedule_config={"cron": "0 0 * * *"},
            node_strategy="auto",
        )
        s.add(t)
        await s.flush()
        s.add(TaskRun(id=run_id, task_id=t.id, status=RunStatus.SUCCESS, log_file_path=log_path))
        await s.commit()

    rsp = await client.get(
        f"/api/v1/tasks/runs/{run_id}/logs",
        headers={"Authorization": f"Bearer {alice_t}"},
    )
    assert rsp.status_code == 404
