"""add_project_new_fields

Revision ID: c55f12a34567
Revises: b44e04019896
Create Date: 2026-05-15 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c55f12a34567'
down_revision: Union[str, Sequence[str], None] = 'b44e04019896'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add new fields to projects table."""
    op.add_column('projects', sa.Column('work_path', sa.String(length=256), nullable=False, server_default='/'))
    op.add_column('projects', sa.Column('git_branch', sa.String(length=128), nullable=True))
    op.add_column('projects', sa.Column('git_username', sa.String(length=128), nullable=True))
    op.add_column('projects', sa.Column('git_token', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('worker_id', sa.UUID(), nullable=True))
    op.add_column('projects', sa.Column('environment_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_projects_environment_id', 'projects', 'environments', ['environment_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Remove new fields from projects table."""
    op.drop_constraint('fk_projects_environment_id', 'projects', type_='foreignkey')
    op.drop_column('projects', 'environment_id')
    op.drop_column('projects', 'worker_id')
    op.drop_column('projects', 'git_token')
    op.drop_column('projects', 'git_username')
    op.drop_column('projects', 'git_branch')
    op.drop_column('projects', 'work_path')
