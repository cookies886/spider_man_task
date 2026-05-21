"""Python source build (master-local).

Async pipeline:
1. Download tarball to {SCRATCH}/{version}.tar.xz
2. Extract to {SCRATCH}/{version}/
3. ./configure --prefix={INSTALL}/{version}
4. make -j$(nproc)
5. make install

Build log streamed to {build_log_path}.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.database import async_session
from app.models.environment import PythonVersion, PyVerStatus

logger = logging.getLogger(__name__)

PY_INSTALL_ROOT = Path(os.environ.get("PY_INSTALL_ROOT", "/tmp/spiderman/pythons"))
PY_BUILD_ROOT = Path(os.environ.get("PY_BUILD_ROOT", "/tmp/spiderman/py-build"))
PY_LOG_ROOT = Path(os.environ.get("PY_LOG_ROOT", "/tmp/spiderman/py-logs"))


async def build_python_version(version_id: uuid.UUID) -> None:
    PY_INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    PY_BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    PY_LOG_ROOT.mkdir(parents=True, exist_ok=True)

    async with async_session() as s:
        pv = (
            await s.execute(
                select(PythonVersion).where(PythonVersion.id == version_id)
            )
        ).scalar_one_or_none()
        if pv is None:
            return
        version = pv.version
        url = pv.tarball_url
        log_path = PY_LOG_ROOT / f"{version}.log"
        pv.build_log_path = str(log_path)
        await s.commit()

    install_path = PY_INSTALL_ROOT / version
    build_dir = PY_BUILD_ROOT / version
    tarball = PY_BUILD_ROOT / f"{version}.tar.xz"

    log_fh = open(log_path, "w", buffering=1)

    def log(msg: str) -> None:
        log_fh.write(msg.rstrip() + "\n")

    async def _set_status(status: PyVerStatus, error: str | None = None) -> None:
        async with async_session() as s2:
            pv = (
                await s2.execute(
                    select(PythonVersion).where(PythonVersion.id == version_id)
                )
            ).scalar_one()
            pv.status = status
            if error is not None:
                pv.error_msg = error[:500]
            if status == PyVerStatus.READY:
                pv.install_path = str(install_path)
            await s2.commit()

    async def _run(cmd: list[str], cwd: Path | None = None) -> int:
        log(f"$ {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout
        async for raw in proc.stdout:
            try:
                log(raw.decode("utf-8", errors="replace").rstrip())
            except Exception:
                pass
        return await proc.wait()

    try:
        await _set_status(PyVerStatus.DOWNLOADING)
        log(f"Downloading {url} ...")
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            tarball.write_bytes(resp.content)
        log(f"Downloaded {tarball} ({tarball.stat().st_size} bytes)")

        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True)

        await _set_status(PyVerStatus.BUILDING)
        rc = await _run(["tar", "-xJf", str(tarball), "-C", str(build_dir), "--strip-components=1"])
        if rc != 0:
            raise RuntimeError(f"tar exit={rc}")

        rc = await _run(
            ["./configure", f"--prefix={install_path}", "--enable-optimizations"],
            cwd=build_dir,
        )
        if rc != 0:
            raise RuntimeError(f"configure exit={rc}")

        nproc = os.cpu_count() or 2
        rc = await _run(["make", f"-j{nproc}"], cwd=build_dir)
        if rc != 0:
            raise RuntimeError(f"make exit={rc}")

        rc = await _run(["make", "install"], cwd=build_dir)
        if rc != 0:
            raise RuntimeError(f"make install exit={rc}")

        log("BUILD SUCCESS")
        await _set_status(PyVerStatus.READY)
    except Exception as e:
        log(f"BUILD FAILED: {e}")
        await _set_status(PyVerStatus.FAILED, error=str(e))
    finally:
        log_fh.close()
