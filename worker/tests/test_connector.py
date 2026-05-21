import asyncio

import pytest
import websockets

from agent.connector import Connector


@pytest.mark.asyncio
async def test_connector_register_and_heartbeat():
    received = []
    server_done = asyncio.Event()

    async def server_handler(ws):
        try:
            async for msg in ws:
                received.append(msg)
                if len(received) >= 2:
                    server_done.set()
                    break
        except websockets.ConnectionClosed:
            pass

    server = await websockets.serve(server_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    config = type(
        "C",
        (),
        dict(
            master_url=f"ws://127.0.0.1:{port}",
            api_key="k",
            node_id="n",
            node_name="t",
            listen_port=8001,
            heartbeat_interval=5,
            work_dir="/tmp",
        ),
    )()

    async def on_frame(_f):
        pass

    conn = Connector(config, on_frame=on_frame)
    task = asyncio.create_task(conn.run_once())

    # Wait briefly for connection, then send two frames
    for _ in range(20):
        if conn._ws is not None:
            break
        await asyncio.sleep(0.05)

    await conn.send({"type": "register", "os": "linux", "arch": "x86_64",
                     "python_version": "3.12", "ip": "127.0.0.1"})
    await conn.send({"type": "heartbeat", "cpu": 1, "mem": 1, "disk": 1,
                     "net_in": 0, "net_out": 0, "running": 0})

    try:
        await asyncio.wait_for(server_done.wait(), timeout=3)
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        server.close()
        await server.wait_closed()

    assert len(received) >= 2
