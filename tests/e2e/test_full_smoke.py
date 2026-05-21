"""Full end-to-end smoke covering all 7 slices.

Run with the master and master_local worker up:
  cd backend && uvicorn app.main:app ... &
  spiderman-worker ... (with master_local creds) &
  pytest tests/e2e/test_full_smoke.py -v
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import time
import uuid
import zipfile

import httpx
import pytest
import websockets


MASTER = os.environ.get("E2E_MASTER", "http://localhost:8000")
WS_BASE = MASTER.replace("http://", "ws://").replace("https://", "wss://")


def _login(c: httpx.Client) -> str:
    r = c.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_client():
    with httpx.Client(base_url=MASTER, timeout=20) as c:
        token = _login(c)
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


@pytest.fixture(scope="module")
def admin_token():
    with httpx.Client(base_url=MASTER, timeout=20) as c:
        return _login(c)


# ---- Slice 1: master_local online ----


def test_slice1_master_local_online(admin_client: httpx.Client):
    for _ in range(20):
        r = admin_client.get("/api/v1/workers")
        items = r.json().get("items", [])
        ml = next((w for w in items if w["node_id"] == "master-local"), None)
        if ml and ml["status"] == "online":
            return
        time.sleep(0.5)
    pytest.fail("master-local never came online")


# ---- Slice 2: RBAC ----


def test_slice2_create_viewer_and_403(admin_client: httpx.Client):
    # create viewer-role user
    r = admin_client.post(
        "/api/v1/users",
        json={
            "username": f"e2e-viewer-{uuid.uuid4().hex[:6]}",
            "password": "viewerpw1234",
            "role_codes": ["viewer"],
            "page_acls": ["dashboard"],
        },
    )
    assert r.status_code == 201
    username = r.json()["username"]

    # log in as viewer
    with httpx.Client(base_url=MASTER, timeout=10) as vc:
        vr = vc.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "viewerpw1234"},
        ).json()
        vt = vr["access_token"]
        # /me should reflect non-superuser + page_acls=[dashboard]
        me = vc.get("/api/v1/me", headers={"Authorization": f"Bearer {vt}"}).json()
        assert me["is_superuser"] is False
        assert me["page_acls"] == ["dashboard"]
        # /users/list is superuser-only → 403
        r = vc.get("/api/v1/users", headers={"Authorization": f"Bearer {vt}"})
        assert r.status_code == 403
        # POST /workers requires worker.manage → 403 for viewer
        r = vc.post(
            "/api/v1/workers",
            headers={"Authorization": f"Bearer {vt}"},
            json={"name": "x", "hostname": "x", "ip": "1.1.1.1"},
        )
        assert r.status_code == 403


# ---- Slice 3: project + file edit ----


@pytest.fixture(scope="module")
def smoke_project(admin_client: httpx.Client):
    # Build small zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("MyProj/main.py", "print('v1')\n")
    buf.seek(0)
    name = f"smoke-zip-{uuid.uuid4().hex[:6]}"
    r = admin_client.post(
        "/api/v1/projects",
        data={"body": json.dumps({"name": name, "source_type": "zip"})},
        files={"file": ("p.zip", buf.getvalue(), "application/zip")},
    )
    assert r.status_code == 201
    pid = r.json()["id"]
    yield pid
    admin_client.delete(f"/api/v1/projects/{pid}")


def test_slice3_zip_extract_and_work_path(
    admin_client: httpx.Client, smoke_project: str
):
    r = admin_client.get(f"/api/v1/projects/{smoke_project}").json()
    assert r["work_path"] == "/MyProj"
    assert r["current_hash"]


def test_slice3_file_edit(admin_client: httpx.Client, smoke_project: str):
    r = admin_client.get(
        f"/api/v1/projects/{smoke_project}/file?path=/MyProj/main.py"
    )
    assert r.status_code == 200
    assert "v1" in r.json()["content"]

    r = admin_client.put(
        f"/api/v1/projects/{smoke_project}/file?path=/MyProj/main.py",
        json={"content": "print('v2 edited')\n"},
    )
    assert r.status_code == 200
    new_hash = r.json()["hash"]

    # Round-trip read
    after = admin_client.get(
        f"/api/v1/projects/{smoke_project}/file?path=/MyProj/main.py"
    ).json()
    assert "v2 edited" in after["content"]
    # Hash bumped on the project
    detail = admin_client.get(f"/api/v1/projects/{smoke_project}").json()
    assert detail["current_hash"] == new_hash


def test_slice3_internal_zip_fetch_auth(
    admin_client: httpx.Client, smoke_project: str
):
    # Bad token rejected
    r = httpx.get(
        f"{MASTER}/api/v1/projects/{smoke_project}/zip",
        params={"node_id": "master-local", "token": "WRONG"},
    )
    assert r.status_code == 401
    # Good token → 200 zip
    r = httpx.get(
        f"{MASTER}/api/v1/projects/{smoke_project}/zip",
        params={
            "node_id": "master-local",
            "token": "dev-master-local-key",
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


# ---- Slice 4: task + run + live log ----


@pytest.fixture(scope="module")
def smoke_task(admin_client: httpx.Client, smoke_project: str):
    name = f"smoke-task-{uuid.uuid4().hex[:6]}"
    r = admin_client.post(
        "/api/v1/tasks",
        json={
            "name": name,
            "project_id": smoke_project,
            "command": "echo hello-from-e2e && python3 -c 'print(42)'",
            "schedule_type": "immediate",
            "timeout_sec": 30,
        },
    )
    assert r.status_code == 201
    tid = r.json()["id"]
    yield tid
    admin_client.delete(f"/api/v1/tasks/{tid}")


def test_slice4_run_to_success(admin_client: httpx.Client, smoke_task: str):
    rr = admin_client.post(f"/api/v1/tasks/{smoke_task}/run")
    assert rr.status_code == 200
    run_id = rr.json()["run_id"]
    # Poll
    for _ in range(20):
        runs = admin_client.get(f"/api/v1/tasks/{smoke_task}/runs").json()["items"]
        latest = next((x for x in runs if x["id"] == run_id), None)
        if latest and latest["status"] in ("success", "failed", "timeout", "killed"):
            assert latest["status"] == "success"
            assert latest["exit_code"] == 0
            return
        time.sleep(0.5)
    pytest.fail("run never finished")


@pytest.mark.asyncio
async def test_slice4_live_log_streaming(admin_token: str, smoke_project: str):
    # Long-running task to capture log
    async with httpx.AsyncClient(base_url=MASTER, timeout=20) as c:
        c.headers["Authorization"] = f"Bearer {admin_token}"
        name = f"smoke-slow-{uuid.uuid4().hex[:6]}"
        tr = await c.post(
            "/api/v1/tasks",
            json={
                "name": name,
                "project_id": smoke_project,
                "command": "for i in 1 2 3 4 5; do echo line-$i; sleep 0.2; done",
                "schedule_type": "immediate",
                "timeout_sec": 15,
            },
        )
        assert tr.status_code == 201
        tid = tr.json()["id"]
        run_resp = await c.post(f"/api/v1/tasks/{tid}/run")
        run_id = run_resp.json()["run_id"]

        received: list[str] = []
        done = asyncio.Event()

        async def consumer():
            async with websockets.connect(f"{WS_BASE}/ws/runs/{run_id}/logs") as ws:
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        f = json.loads(msg)
                        if "line" in f:
                            received.append(f["line"])
                        elif f.get("event") == "task_done":
                            done.set()
                            return
                except asyncio.TimeoutError:
                    return

        ct = asyncio.create_task(consumer())
        await asyncio.wait_for(done.wait(), timeout=20)
        ct.cancel()
        try:
            await ct
        except (asyncio.CancelledError, Exception):
            pass

        assert any("line-" in l for l in received), f"no lines captured: {received}"

        await c.delete(f"/api/v1/tasks/{tid}")


def test_slice4_dependency_chain(admin_client: httpx.Client, smoke_project: str):
    up_r = admin_client.post(
        "/api/v1/tasks",
        json={
            "name": f"e2e-up-{uuid.uuid4().hex[:6]}",
            "project_id": smoke_project,
            "command": "echo upstream",
            "schedule_type": "immediate",
        },
    ).json()
    up_id = up_r["id"]
    down_r = admin_client.post(
        "/api/v1/tasks",
        json={
            "name": f"e2e-down-{uuid.uuid4().hex[:6]}",
            "project_id": smoke_project,
            "command": "echo downstream",
            "schedule_type": "immediate",
            "depends_on": [up_id],
        },
    ).json()
    down_id = down_r["id"]
    admin_client.post(f"/api/v1/tasks/{up_id}/run")

    for _ in range(30):
        runs = admin_client.get(f"/api/v1/tasks/{down_id}/runs").json()["items"]
        if runs and runs[0]["status"] == "success":
            assert runs[0]["triggered_by"] == "dependency"
            admin_client.delete(f"/api/v1/tasks/{up_id}")
            admin_client.delete(f"/api/v1/tasks/{down_id}")
            return
        time.sleep(0.5)
    pytest.fail("downstream never triggered + succeeded")


# ---- Slice 5: env + mirrors ----


def test_slice5_mirrors_seeded(admin_client: httpx.Client):
    r = admin_client.get("/api/v1/mirror-sources").json()
    names = {m["name"] for m in r}
    assert names >= {"PyPI 官方", "阿里云", "清华大学"}


def test_slice5_create_env_to_ready(admin_client: httpx.Client):
    name = f"e2e-env-{uuid.uuid4().hex[:6]}"
    r = admin_client.post(
        "/api/v1/environments",
        json={"name": name, "description": "e2e", "requirements": ""},
    )
    assert r.status_code == 201
    eid = r.json()["id"]
    for _ in range(20):
        d = admin_client.get(f"/api/v1/environments/{eid}").json()
        if d["status"] == "ready":
            assert d["venv_path"]
            admin_client.delete(f"/api/v1/environments/{eid}")
            return
        if d["status"] == "failed":
            pytest.fail(f"env failed: {d.get('error_msg')}")
        time.sleep(0.5)
    pytest.fail("env never ready")


# ---- Slice 6: dashboard ----


def test_slice6_dashboard_endpoints(admin_client: httpx.Client):
    o = admin_client.get("/api/v1/dashboard/overview").json()
    assert "total_projects" in o
    assert "cluster_health" in o
    p = admin_client.get("/api/v1/dashboard/perf?range=24h").json()
    assert "series" in p and "workers" in p
    t = admin_client.get("/api/v1/dashboard/tasks?range=24h").json()
    assert "summary" in t and "calendar" in t
    g = admin_client.get("/api/v1/dashboard/gantt").json()
    assert "items" in g


# ---- Slice 7: ops ----


def test_slice7_persistent_files(admin_client: httpx.Client):
    folder = f"/e2e-{uuid.uuid4().hex[:6]}"
    r = admin_client.post(f"/api/v1/files/folder?path={folder}")
    assert r.status_code == 200
    files = {
        "file": ("hello.txt", b"hello e2e\n", "text/plain"),
    }
    # Need to drop bearer header conflict (httpx adds CT for multipart)
    r = admin_client.post(f"/api/v1/files/upload?path={folder}", files=files)
    assert r.status_code == 200
    assert r.json()["path"].endswith("/hello.txt")
    listing = admin_client.get(f"/api/v1/files?path={folder}").json()
    assert any(x["name"] == "hello.txt" for x in listing)
    # Cleanup
    admin_client.delete(f"/api/v1/files?path={folder}/hello.txt")
    admin_client.delete(f"/api/v1/files?path={folder}")


def test_slice7_notification_channel_crud(admin_client: httpx.Client):
    name = f"e2e-ding-{uuid.uuid4().hex[:6]}"
    r = admin_client.post(
        "/api/v1/notification-channels",
        json={
            "type": "dingtalk",
            "name": name,
            "config": {"webhook": "https://example.invalid/dingtalk"},
        },
    )
    assert r.status_code == 201
    cid = r.json()["id"]
    chans = admin_client.get("/api/v1/notification-channels").json()
    assert any(c["id"] == cid for c in chans)
    admin_client.delete(f"/api/v1/notification-channels/{cid}")


def test_slice7_smtp_settings_roundtrip(admin_client: httpx.Client):
    r = admin_client.put(
        "/api/v1/smtp-settings",
        json={
            "host": "smtp.example.com",
            "port": 465,
            "username": "noreply@example.com",
            "password": "shh",
            "from_addr": "noreply@example.com",
            "use_tls": True,
            "is_enabled": False,
        },
    )
    assert r.status_code == 200
    cur = admin_client.get("/api/v1/smtp-settings").json()
    assert cur["host"] == "smtp.example.com"
    assert cur["port"] == 465
    # password not echoed
    assert "password" not in cur


def test_slice7_log_retention(admin_client: httpx.Client):
    r = admin_client.put(
        "/api/v1/logs/retention",
        json={"days_to_keep": 14, "is_enabled": True},
    )
    assert r.status_code == 200
    cur = admin_client.get("/api/v1/logs/retention").json()
    assert cur["days_to_keep"] == 14
    assert cur["is_enabled"] is True
