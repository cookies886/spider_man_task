"""Virtual environment manager (master-local).

Creates `{VENV_ROOT}/{env_name}/` using the configured PythonVersion's install
binary, then `pip install -i {mirror} -r requirements`. Streams output to
`{install_log_path}`. Slice 5 supports master-local environments only; remote
node envs go through the worker /env/create endpoint (slice 7+).
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session
from app.models.environment import (
    Environment,
    EnvStatus,
    MirrorSource,
    PythonVersion,
    PyVerStatus,
)

logger = logging.getLogger(__name__)

VENV_ROOT = Path(os.environ.get("VENV_ROOT", "/tmp/spiderman/venvs"))
VENV_LOG_ROOT = Path(os.environ.get("VENV_LOG_ROOT", "/tmp/spiderman/venv-logs"))


def _python_bin(install_path: Path | None) -> Path:
    if install_path is not None:
        return install_path / "bin" / "python3"
    return Path(sys.executable)


def _venv_python(venv_path: Path) -> Path:
    return venv_path / ("Scripts" if sys.platform == "win32" else "bin") / "python"


async def _run(cmd: list[str], log_fh, cwd: Path | None = None) -> int:
    log_fh.write(f"$ {' '.join(cmd)}\n")
    log_fh.flush()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout
    async for raw in proc.stdout:
        try:
            log_fh.write(raw.decode("utf-8", errors="replace"))
            log_fh.flush()
        except Exception:
            pass
    return await proc.wait()


async def create_environment(env_id: uuid.UUID) -> None:
    VENV_ROOT.mkdir(parents=True, exist_ok=True)
    VENV_LOG_ROOT.mkdir(parents=True, exist_ok=True)

    async with async_session() as s:
        env = (
            await s.execute(select(Environment).where(Environment.id == env_id))
        ).scalar_one_or_none()
        if env is None:
            return
        pv = None
        if env.python_version_id:
            pv = (
                await s.execute(
                    select(PythonVersion).where(
                        PythonVersion.id == env.python_version_id
                    )
                )
            ).scalar_one_or_none()
        mirror = None
        if env.mirror_id:
            mirror = (
                await s.execute(
                    select(MirrorSource).where(MirrorSource.id == env.mirror_id)
                )
            ).scalar_one_or_none()
        name = env.name
        requirements = env.requirements or ""

    log_path = VENV_LOG_ROOT / f"{name}.log"
    venv_path = VENV_ROOT / name
    log_fh = open(log_path, "w", buffering=1)

    async def _set(status: EnvStatus, error: str | None = None) -> None:
        async with async_session() as s2:
            row = (
                await s2.execute(select(Environment).where(Environment.id == env_id))
            ).scalar_one()
            row.status = status
            row.install_log_path = str(log_path)
            row.venv_path = str(venv_path)
            if error is not None:
                row.error_msg = error[:500]
            await s2.commit()

    try:
        if pv is not None and pv.status != PyVerStatus.READY:
            raise RuntimeError(
                f"python version {pv.version} not ready: {pv.status}"
            )

        if venv_path.exists():
            shutil.rmtree(venv_path)

        await _set(EnvStatus.CREATING)
        py_bin = str(
            _python_bin(Path(pv.install_path))
            if pv and pv.install_path
            else _python_bin(None)
        )
        log_fh.write(f"using python: {py_bin}\n")
        log_fh.flush()

        rc = await _run([py_bin, "-m", "venv", str(venv_path)], log_fh)
        if rc != 0:
            raise RuntimeError(f"venv create exit={rc}")

        if requirements.strip():
            req_path = venv_path / "_requirements.txt"
            req_path.write_text(requirements)
            pip_args = [str(_venv_python(venv_path)), "-m", "pip", "install"]
            if mirror is not None:
                pip_args += ["-i", mirror.url]
            pip_args += ["-r", str(req_path)]
            rc = await _run(pip_args, log_fh)
            if rc != 0:
                raise RuntimeError(f"pip install exit={rc}")

        log_fh.write("ENVIRONMENT READY\n")
        await _set(EnvStatus.READY)
    except Exception as e:
        log_fh.write(f"FAILED: {e}\n")
        await _set(EnvStatus.FAILED, error=str(e))
    finally:
        log_fh.close()
