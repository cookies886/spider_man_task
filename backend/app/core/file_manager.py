"""Project workspace file manager.

Each project has a single working directory at `{DATA_ROOT}/{project_id}/`.
ZIP-based projects extract uploads here. Git-based projects clone here.
After mutations, the workspace gets re-packaged into `{ZIP_ROOT}/{project_id}.zip`
and the project's `current_hash` column is bumped so workers know to re-pull.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

logger = logging.getLogger(__name__)

DATA_ROOT = Path(os.environ.get("PROJECT_DATA_ROOT", "/tmp/spiderman/projects"))
ZIP_ROOT = Path(os.environ.get("PROJECT_ZIP_ROOT", "/tmp/spiderman/zips"))


@dataclass
class FileEntry:
    name: str
    path: str
    is_dir: bool
    size: int
    mtime: datetime


class FileManager:
    def __init__(self, data_root: Path = DATA_ROOT, zip_root: Path = ZIP_ROOT):
        self.data_root = data_root
        self.zip_root = zip_root
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.zip_root.mkdir(parents=True, exist_ok=True)

    def workspace(self, project_id: uuid.UUID) -> Path:
        return self.data_root / str(project_id)

    def zip_path(self, project_id: uuid.UUID) -> Path:
        return self.zip_root / f"{project_id}.zip"

    def _safe_join(self, project_id: uuid.UUID, relative: str) -> Path:
        base = self.workspace(project_id).resolve()
        base.mkdir(parents=True, exist_ok=True)
        rel = (relative or "").lstrip("/")
        target = (base / rel).resolve()
        if base != target and base not in target.parents:
            raise ValueError("path escape detected")
        return target

    async def extract_zip(self, project_id: uuid.UUID, upload: UploadFile) -> str:
        """Replace workspace with ZIP contents. Return inferred work_path."""
        ws = self.workspace(project_id)
        if ws.exists():
            shutil.rmtree(ws)
        ws.mkdir(parents=True)

        data = await upload.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.infolist():
                if ".." in member.filename or member.filename.startswith("/"):
                    continue
                zf.extract(member, ws)

        return self._infer_work_path(ws)

    def _infer_work_path(self, ws: Path) -> str:
        entries = [p for p in ws.iterdir() if not p.name.startswith(".")]
        if len(entries) == 1 and entries[0].is_dir():
            return f"/{entries[0].name}"
        return "/"

    def list_dir(self, project_id: uuid.UUID, rel: str = "") -> list[FileEntry]:
        target = self._safe_join(project_id, rel)
        if not target.exists() or not target.is_dir():
            return []
        out: list[FileEntry] = []
        ws = self.workspace(project_id).resolve()
        for entry in sorted(target.iterdir()):
            try:
                rel_path = "/" + str(entry.resolve().relative_to(ws))
            except ValueError:
                continue
            stat = entry.stat()
            out.append(
                FileEntry(
                    name=entry.name,
                    path=rel_path,
                    is_dir=entry.is_dir(),
                    size=stat.st_size if entry.is_file() else 0,
                    mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )
        return out

    def read_file(self, project_id: uuid.UUID, rel: str) -> str:
        target = self._safe_join(project_id, rel)
        if not target.is_file():
            raise FileNotFoundError(rel)
        if target.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("file too large for inline view")
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, project_id: uuid.UUID, rel: str, content: str) -> None:
        target = self._safe_join(project_id, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def delete_file(self, project_id: uuid.UUID, rel: str) -> None:
        target = self._safe_join(project_id, rel)
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)

    def repackage(self, project_id: uuid.UUID) -> str:
        """Pack workspace into a zip and return its sha256 hash."""
        ws = self.workspace(project_id)
        zp = self.zip_path(project_id)
        zp.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(ws):
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".venv")]
                for fname in sorted(files):
                    full = Path(root) / fname
                    rel = full.relative_to(ws)
                    zf.write(full, arcname=str(rel))
                    h.update(str(rel).encode())
                    h.update(full.read_bytes())
        return h.hexdigest()

    def remove_workspace(self, project_id: uuid.UUID) -> None:
        ws = self.workspace(project_id)
        if ws.exists():
            shutil.rmtree(ws)
        zp = self.zip_path(project_id)
        if zp.exists():
            zp.unlink()


file_manager = FileManager()
