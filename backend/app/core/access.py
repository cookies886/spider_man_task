"""Access-scope helpers for owner+collaborator visibility.

Returns SQLAlchemy WHERE fragments callers can apply to their queries.
For superusers, returns None (no filter).
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.sql import ColumnElement

from app.models.environment import Environment, EnvironmentCollaborator
from app.models.project import Project, ProjectCollaborator
from app.models.user import User


def project_visibility_clause(user: User) -> ColumnElement | None:
    """None means superuser — apply no filter. Else returns owner-or-collab predicate."""
    if user.is_superuser:
        return None
    return or_(
        Project.owner_id == user.id,
        Project.id.in_(
            select(ProjectCollaborator.project_id).where(
                ProjectCollaborator.user_id == user.id
            )
        ),
    )


def env_visibility_clause(user: User) -> ColumnElement | None:
    if user.is_superuser:
        return None
    return or_(
        Environment.owner_id == user.id,
        Environment.id.in_(
            select(EnvironmentCollaborator.env_id).where(
                EnvironmentCollaborator.user_id == user.id
            )
        ),
    )


async def user_can_read_project(session, user: User, project_id) -> bool:
    if user.is_superuser:
        return (
            await session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none() is not None
    row = await session.execute(
        select(Project.id).where(
            Project.id == project_id,
            or_(
                Project.owner_id == user.id,
                Project.id.in_(
                    select(ProjectCollaborator.project_id).where(
                        ProjectCollaborator.user_id == user.id
                    )
                ),
            ),
        )
    )
    return row.scalar_one_or_none() is not None


async def user_can_write_project(session, user: User, project_id) -> bool:
    """Owner / collaborator / superuser can write. Use for update/run."""
    return await user_can_read_project(session, user, project_id)


async def user_owns_project(session, user: User, project_id) -> bool:
    """Owner / superuser can hard-mutate (delete / manage collaborators)."""
    if user.is_superuser:
        return (
            await session.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none() is not None
    row = await session.execute(
        select(Project.id).where(
            Project.id == project_id, Project.owner_id == user.id
        )
    )
    return row.scalar_one_or_none() is not None


async def user_can_read_env(session, user: User, env_id) -> bool:
    if user.is_superuser:
        return (
            await session.execute(
                select(Environment).where(Environment.id == env_id)
            )
        ).scalar_one_or_none() is not None
    row = await session.execute(
        select(Environment.id).where(
            Environment.id == env_id,
            or_(
                Environment.owner_id == user.id,
                Environment.id.in_(
                    select(EnvironmentCollaborator.env_id).where(
                        EnvironmentCollaborator.user_id == user.id
                    )
                ),
            ),
        )
    )
    return row.scalar_one_or_none() is not None


async def user_can_write_env(session, user: User, env_id) -> bool:
    return await user_can_read_env(session, user, env_id)


async def user_owns_env(session, user: User, env_id) -> bool:
    if user.is_superuser:
        return (
            await session.execute(
                select(Environment).where(Environment.id == env_id)
            )
        ).scalar_one_or_none() is not None
    row = await session.execute(
        select(Environment.id).where(
            Environment.id == env_id, Environment.owner_id == user.id
        )
    )
    return row.scalar_one_or_none() is not None
