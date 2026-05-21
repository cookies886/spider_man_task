"""worker ws fields

Revision ID: 72df796b3507
Revises: c55f12a34567
Create Date: 2026-05-18 11:42:28.436645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "72df796b3507"
down_revision: Union[str, Sequence[str], None] = "c55f12a34567"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workers", sa.Column("node_id", sa.String(length=64), nullable=True))
    op.add_column("workers", sa.Column("name", sa.String(length=128), nullable=True))
    op.add_column(
        "workers",
        sa.Column("type", sa.String(length=16), server_default="remote", nullable=False),
    )
    op.add_column("workers", sa.Column("os", sa.String(length=32), nullable=True))
    op.add_column("workers", sa.Column("arch", sa.String(length=32), nullable=True))
    op.add_column("workers", sa.Column("python_version", sa.String(length=32), nullable=True))
    op.add_column(
        "workers",
        sa.Column("api_key_hash", sa.String(length=128), server_default="", nullable=False),
    )
    op.execute("UPDATE workers SET node_id = id::text WHERE node_id IS NULL")
    op.execute("UPDATE workers SET name = hostname WHERE name IS NULL")
    op.alter_column("workers", "node_id", nullable=False)
    op.alter_column("workers", "name", nullable=False)
    op.create_index("ix_workers_node_id", "workers", ["node_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_workers_node_id", table_name="workers")
    op.drop_column("workers", "api_key_hash")
    op.drop_column("workers", "python_version")
    op.drop_column("workers", "arch")
    op.drop_column("workers", "os")
    op.drop_column("workers", "type")
    op.drop_column("workers", "name")
    op.drop_column("workers", "node_id")
