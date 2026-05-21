import pytest

from app.core.worker_registry import WorkerRegistry


class FakeWS:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = True


@pytest.mark.asyncio
async def test_register_and_send():
    reg = WorkerRegistry()
    ws = FakeWS()
    await reg.register("node-1", ws)
    assert reg.is_online("node-1")
    ok = await reg.send("node-1", {"type": "ping"})
    assert ok
    assert ws.sent == [{"type": "ping"}]


@pytest.mark.asyncio
async def test_send_to_missing_returns_false():
    reg = WorkerRegistry()
    assert (await reg.send("ghost", {"type": "x"})) is False


@pytest.mark.asyncio
async def test_unregister_drops_connection():
    reg = WorkerRegistry()
    ws = FakeWS()
    await reg.register("n", ws)
    await reg.unregister("n")
    assert not reg.is_online("n")


@pytest.mark.asyncio
async def test_double_register_replaces_and_closes_old():
    reg = WorkerRegistry()
    old, new = FakeWS(), FakeWS()
    await reg.register("n", old)
    await reg.register("n", new)
    assert old.closed
    assert reg.is_online("n")


@pytest.mark.asyncio
async def test_online_node_ids_lists_keys():
    reg = WorkerRegistry()
    await reg.register("a", FakeWS())
    await reg.register("b", FakeWS())
    assert set(reg.online_node_ids()) == {"a", "b"}
