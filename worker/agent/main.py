"""Worker entry point.

Composition:
  - Connector: maintains WS to master.
  - Heartbeat loop: every cfg.heartbeat_interval seconds, send a sampled frame.
  - Frame router: handles task.run / task.kill from master, spawns Executor jobs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone

from agent.config import WorkerConfig, system_info
from agent.connector import Connector
from agent.executor import run_subprocess
from agent.heartbeat import sample

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("spiderman.worker")


class WorkerRuntime:
    def __init__(self, cfg: WorkerConfig):
        self.cfg = cfg
        self.running_tasks: dict[str, asyncio.Task] = {}
        self.connector: Connector | None = None

    async def on_frame(self, frame: dict) -> None:
        t = frame.get("type")
        if t == "register.ack":
            logger.info("registered as %s", frame.get("node_id"))
        elif t == "task.run":
            await self._start_run(frame)
        elif t == "task.kill":
            await self._kill_run(frame.get("run_id"))

    async def _start_run(self, frame: dict) -> None:
        run_id = frame.get("run_id")
        if not run_id or run_id in self.running_tasks:
            return
        cmd = frame.get("command", "")
        timeout = int(frame.get("timeout_sec", 3600))
        env_vars = frame.get("env_vars") or {}
        connector = self.connector

        subdir = frame.get("subdir") or "_no_project"
        project_root = os.path.join(self.cfg.work_dir, subdir.split("/")[0]) if "/" in subdir else os.path.join(self.cfg.work_dir, subdir)
        cwd = os.path.join(self.cfg.work_dir, subdir)
        os.makedirs(cwd, exist_ok=True)

        # Fetch project zip if hash mismatch (best-effort; task can still run without)
        await self._sync_project(
            project_id=frame.get("project_id"),
            zip_url=frame.get("project_files_url"),
            expected_hash=frame.get("expected_hash"),
            project_root=project_root,
        )

        async def on_line(line: str, stream: str):
            if connector is None:
                return
            await connector.send({
                "type": "task.log",
                "run_id": run_id,
                "line": line,
                "stream": stream,
                "ts": datetime.now(timezone.utc).isoformat(),
            })

        async def runner():
            try:
                rc = await run_subprocess(cmd, cwd, env_vars, on_line, timeout)
                kind = "task.killed" if rc == 124 else "task.done"
                payload = {"type": kind, "run_id": run_id, "exit_code": rc}
                if rc == 124:
                    payload["reason"] = "timeout"
                if connector is not None:
                    await connector.send(payload)
            except asyncio.CancelledError:
                if connector is not None:
                    await connector.send(
                        {
                            "type": "task.killed",
                            "run_id": run_id,
                            "exit_code": -1,
                            "reason": "killed_by_master",
                        }
                    )
                raise
            finally:
                self.running_tasks.pop(run_id, None)

        self.running_tasks[run_id] = asyncio.create_task(runner())

    async def _sync_project(
        self,
        project_id: str | None,
        zip_url: str | None,
        expected_hash: str | None,
        project_root: str,
    ) -> None:
        """If we don't already have project files at the expected hash, fetch and unpack."""
        if not project_id or not zip_url or not expected_hash:
            return
        marker = os.path.join(project_root, ".spiderman_hash")
        os.makedirs(project_root, exist_ok=True)
        try:
            with open(marker, "r") as fh:
                if fh.read().strip() == expected_hash:
                    return
        except FileNotFoundError:
            pass

        import shutil
        import zipfile
        import io
        import httpx

        full_url = self.cfg.master_url.replace("ws://", "http://").replace(
            "wss://", "https://"
        ) + zip_url + f"&token={self.cfg.api_key}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(full_url)
                r.raise_for_status()
                # Wipe and re-extract
                for entry in os.listdir(project_root):
                    p = os.path.join(project_root, entry)
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    else:
                        os.unlink(p)
                with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                    zf.extractall(project_root)
                with open(marker, "w") as fh:
                    fh.write(expected_hash)
                logger.info(
                    "synced project %s @ %s", project_id, expected_hash[:8]
                )
        except Exception:
            logger.exception("project sync failed; proceeding with stale files")

    async def _kill_run(self, run_id: str | None) -> None:
        task = self.running_tasks.get(run_id) if run_id else None
        if task and not task.done():
            task.cancel()

    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(self.cfg.heartbeat_interval)
            if self.connector is None:
                continue
            await self.connector.send(sample(len(self.running_tasks)))

    async def register_when_connected(self):
        # Wait until we have a live connection, then send register frame.
        while True:
            await asyncio.sleep(0.5)
            if self.connector is None:
                continue
            ok = await self.connector.send(
                {"type": "register", **system_info(), "ip": "0.0.0.0"}
            )
            if ok:
                return


async def amain():
    cfg = WorkerConfig.from_env()
    runtime = WorkerRuntime(cfg)
    runtime.connector = Connector(cfg, on_frame=runtime.on_frame)

    stop = asyncio.Event()

    def _stop(*_):
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass  # Windows

    tasks = [
        asyncio.create_task(runtime.connector.run()),
        asyncio.create_task(runtime.heartbeat_loop()),
        asyncio.create_task(runtime.register_when_connected()),
    ]
    try:
        await stop.wait()
    finally:
        for t in tasks:
            t.cancel()


def run():
    asyncio.run(amain())


if __name__ == "__main__":
    run()
