"""create command table

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11 15:23:26.511493

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "command",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "completed", "failed", native_enum=False),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        # Double is generic and strict pyright wants the parameter.
        sa.Column("not_before", sa.Double[float](), nullable=True),
        sa.Column("queued_at", sa.Double[float](), nullable=False),
        sa.Column("started_at", sa.Double[float](), nullable=True),
        sa.Column("ended_at", sa.Double[float](), nullable=True),
        sa.Column("result", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("waiting_on", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_command")),
    )
    with op.batch_alter_table("command", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_command_claim"),
            ["status", sa.literal_column("priority DESC"), "queued_at"],
            unique=False,
        )

    with op.batch_alter_table("http_cache", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_http_cache_expires_at"), ["expires_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("http_cache", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_http_cache_expires_at"))

    with op.batch_alter_table("command", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_command_claim"))

    op.drop_table("command")
