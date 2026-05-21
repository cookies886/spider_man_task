import uuid

import pytest

from app.core.worker_registry import WorkerRegistry


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        pass


@pytest.mark.asyncio
async def test_dispatcher_picks_least_loaded_online_worker(monkeypatch):
    from app.core import dispatcher as disp

    reg = WorkerRegistry()
    await reg.register("node-a", FakeWS())
    await reg.register("node-b", FakeWS())
    monkeypatch.setattr(disp, "registry", reg)

    candidates = [
        {"node_id": "node-a", "current_tasks": 3, "max_slots": 4},
        {"node_id": "node-b", "current_tasks": 1, "max_slots": 4},
    ]

    chosen = disp.pick_least_loaded(candidates, online_ids={"node-a", "node-b"})
    assert chosen["node_id"] == "node-b"


@pytest.mark.asyncio
async def test_pick_least_loaded_skips_offline():
    from app.core import dispatcher as disp

    candidates = [
        {"node_id": "node-a", "current_tasks": 0, "max_slots": 4},
        {"node_id": "node-b", "current_tasks": 3, "max_slots": 4},
    ]
    chosen = disp.pick_least_loaded(candidates, online_ids={"node-b"})
    assert chosen["node_id"] == "node-b"


@pytest.mark.asyncio
async def test_send_task_run_frame(monkeypatch):
    from app.core import dispatcher as disp

    reg = WorkerRegistry()
    ws = FakeWS()
    await reg.register("node-x", ws)
    monkeypatch.setattr(disp, "registry", reg)

    run_id = str(uuid.uuid4())
    ok = await disp.send_task_run(
        "node-x",
        {
            "run_id": run_id,
            "command": "echo hi",
            "env_vars": {},
            "timeout_sec": 60,
            "expected_hash": None,
            "project_files_url": None,
        },
    )
    assert ok
    assert ws.sent[0]["type"] == "task.run"
    assert ws.sent[0]["run_id"] == run_id


@pytest.mark.asyncio
async def test_send_task_kill(monkeypatch):
    from app.core import dispatcher as disp

    reg = WorkerRegistry()
    ws = FakeWS()
    await reg.register("node-y", ws)
    monkeypatch.setattr(disp, "registry", reg)

    ok = await disp.send_task_kill("node-y", "rid-1", "TERM")
    assert ok
    assert ws.sent[0] == {"type": "task.kill", "run_id": "rid-1", "signal": "TERM"}
