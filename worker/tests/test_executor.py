import shlex
import sys

import pytest

from agent.executor import run_subprocess


PY = shlex.quote(sys.executable)


@pytest.mark.asyncio
async def test_run_subprocess_streams_lines():
    lines = []

    async def on_line(line: str, stream: str):
        lines.append((stream, line))

    rc = await run_subprocess(
        cmd=f'{PY} -c "import sys; print(\'hi\'); print(\'err\', file=sys.stderr)"',
        cwd=".",
        env={"PYTHONUNBUFFERED": "1"},
        on_line=on_line,
        timeout_sec=10,
    )
    assert rc == 0
    streams = {l[0] for l in lines}
    assert "stdout" in streams and "stderr" in streams
    msgs = [l[1] for l in lines]
    assert "hi" in msgs
    assert "err" in msgs


@pytest.mark.asyncio
async def test_run_subprocess_times_out():
    lines = []

    async def on_line(line, stream):
        lines.append(line)

    rc = await run_subprocess(
        cmd=f'{PY} -c "import time; time.sleep(5)"',
        cwd=".",
        env={},
        on_line=on_line,
        timeout_sec=1,
    )
    assert rc != 0
