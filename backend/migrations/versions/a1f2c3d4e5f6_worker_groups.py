"""worker_groups table + group_id FK on workers

Revision ID: a1f2c3d4e5f6
Revises: 57a541968204
Create Date: 2026-05-18 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1f2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "57a541968204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_groups",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_worker_groups_name"), "worker_groups", ["name"], unique=False
    )

    op.add_column("workers", sa.Column("group_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "workers_group_id_fkey",
        "workers",
        "worker_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_workers_group_id"), "workers", ["group_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workers_group_id"), table_name="workers")
    op.drop_constraint("workers_group_id_fkey", "workers", type_="foreignkey")
    op.drop_column("workers", "group_id")
    op.drop_index(op.f("ix_worker_groups_name"), table_name="worker_groups")
    op.drop_table("worker_groups")
