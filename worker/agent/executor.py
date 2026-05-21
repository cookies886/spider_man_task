"""Subprocess runner with line-by-line streaming and timeout."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

OnLine = Callable[[str, str], Awaitable[None]]


async def run_subprocess(
    cmd: str,
    cwd: str,
    env: dict,
    on_line: OnLine,
    timeout_sec: int,
) -> int:
    """Spawn `cmd` via shell, capture stdout/stderr line by line.
    Calls on_line(line, stream) for each line. Returns process exit code.
    On timeout: SIGTERM, wait 5s, SIGKILL. Returns 124 on timeout."""
    full_env = {**os.environ, **env}
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=full_env,
    )

    async def pump(stream: asyncio.StreamReader, name: str):
        while True:
            line = await stream.readline()
            if not line:
                break
            try:
                text = line.decode("utf-8", errors="replace").rstrip("\n")
            except Exception:
                text = "<decode error>"
            try:
                await on_line(text, name)
            except Exception:
                logger.exception("on_line callback failed")

    pumps = asyncio.gather(
        pump(proc.stdout, "stdout"),
        pump(proc.stderr, "stderr"),
    )

    try:
        rc = await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
        await pumps
        return 124
    except asyncio.CancelledError:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
        try:
            await pumps
        except Exception:
            pass
        raise

    await pumps
    return rc
