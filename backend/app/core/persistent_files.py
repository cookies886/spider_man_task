"""Persistent file manager.

Stores files at `{PERSISTENT_ROOT}/...` with arbitrary subdirectories. Provides
safe path operations that block `..` traversal.
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

logger = logging.getLogger(__name__)

_RAW_PERSISTENT_ROOT = Path(
    os.environ.get("PERSISTENT_ROOT", "/tmp/spiderman/persistentMappedAddress")
)
_RAW_PERSISTENT_ROOT.mkdir(parents=True, exist_ok=True)
PERSISTENT_ROOT = _RAW_PERSISTENT_ROOT.resolve()


def _safe_join(rel: str) -> Path:
    base = PERSISTENT_ROOT.resolve()
    base.mkdir(parents=True, exist_ok=True)
    target = (base / (rel or "").lstrip("/")).resolve()
    if base != target and base not in target.parents:
        raise ValueError("path escape detected")
    return target


class PersistentFileManager:
    def list_dir(self, rel: str = "") -> list[dict]:
        target = _safe_join(rel)
        if not target.exists() or not target.is_dir():
            return []
        out: list[dict] = []
        for entry in sorted(target.iterdir()):
            stat = entry.stat()
            out.append(
                {
                    "name": entry.name,
                    "path": "/" + str(entry.relative_to(PERSISTENT_ROOT)),
                    "is_dir": entry.is_dir(),
                    "size": stat.st_size if entry.is_file() else 0,
                    "mtime": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )
        return out

    def make_dir(self, rel: str) -> None:
        target = _safe_join(rel)
        target.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, rel_dir: str, upload: UploadFile) -> str:
        target_dir = _safe_join(rel_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / upload.filename
        with open(target, "wb") as fh:
            data = await upload.read()
            fh.write(data)
        return "/" + str(target.relative_to(PERSISTENT_ROOT))

    def delete(self, rel: str) -> None:
        target = _safe_join(rel)
        if target == PERSISTENT_ROOT.resolve():
            raise ValueError("cannot delete root")
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)

    def open_for_download(self, rel: str) -> Path:
        target = _safe_join(rel)
        if not target.is_file():
            raise FileNotFoundError(rel)
        return target

    def script_path(self, rel: str) -> str:
        return f"/app/../static/persistentMappedAddress/{rel.lstrip('/')}"


persistent_files = PersistentFileManager()
