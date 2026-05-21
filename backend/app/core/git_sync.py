"""Git sync service.

Clones / pulls a Git repo into the project's workspace at
`{DATA_ROOT}/{project_id}/`. After each successful sync, repackages the
workspace and bumps `Project.current_hash`.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.file_manager import file_manager
from app.models.project import GitRepo, Project

logger = logging.getLogger(__name__)


async def _run(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode(errors="replace").strip(),
        stderr.decode(errors="replace").strip(),
    )


def _embed_credentials(url: str, username: str | None, password: str | None) -> str:
    if not username and not password:
        return url
    parsed = urlparse(url)
    auth = quote(username or "", safe="")
    if password:
        auth = f"{auth}:{quote(password, safe='')}"
    netloc = f"{auth}@{parsed.netloc}"
    return urlunparse(parsed._replace(netloc=netloc))


class GitSyncResult:
    def __init__(self, last_commit: str, files_changed: int):
        self.last_commit = last_commit
        self.files_changed = files_changed
        self.last_sync_at = datetime.now(timezone.utc)


class GitSyncService:
    async def sync(
        self, session: AsyncSession, project_id: uuid.UUID
    ) -> GitSyncResult:
        repo_row = await session.execute(
            select(GitRepo).where(GitRepo.project_id == project_id)
        )
        repo = repo_row.scalar_one()

        ws = file_manager.workspace(project_id)
        ws.mkdir(parents=True, exist_ok=True)

        url = _embed_credentials(repo.url, repo.username, repo.password_enc)

        if not (ws / ".git").exists():
            # First-time clone
            for entry in list(ws.iterdir()):
                # Clean any prior contents so clone has a clean target
                if entry.is_dir():
                    import shutil

                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            rc, _out, err = await _run(
                ["clone", "--depth", "1", "--branch", repo.branch, url, "."],
                cwd=ws,
            )
            if rc != 0:
                repo.last_error = err[:500]
                await session.commit()
                raise RuntimeError(f"git clone failed: {err}")
        else:
            # Pull
            rc, _out, err = await _run(
                ["pull", "--ff-only", "origin", repo.branch], cwd=ws
            )
            if rc != 0:
                # Try fetch + reset for non-FF cases
                rc2, _o2, e2 = await _run(["fetch", "origin", repo.branch], cwd=ws)
                if rc2 != 0:
                    repo.last_error = (e2 or err)[:500]
                    await session.commit()
                    raise RuntimeError(f"git fetch failed: {e2 or err}")
                rc3, _o3, e3 = await _run(
                    ["reset", "--hard", f"origin/{repo.branch}"], cwd=ws
                )
                if rc3 != 0:
                    repo.last_error = e3[:500]
                    await session.commit()
                    raise RuntimeError(f"git reset failed: {e3}")

        rc, commit, _err = await _run(["rev-parse", "HEAD"], cwd=ws)
        last_commit = commit if rc == 0 else "unknown"

        new_hash = file_manager.repackage(project_id)
        proj = (
            await session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one()
        files_changed = 0 if proj.current_hash == new_hash else 1
        proj.current_hash = new_hash

        repo.last_commit = last_commit
        repo.last_sync_at = datetime.now(timezone.utc)
        repo.last_error = None
        await session.commit()

        return GitSyncResult(last_commit=last_commit, files_changed=files_changed)


git_sync_service = GitSyncService()
