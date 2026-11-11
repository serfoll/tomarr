"""create http_cache table

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11 13:05:48.028238

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "http_cache",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("adapter", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        # Double is generic and strict pyright wants the parameter.
        sa.Column("expires_at", sa.Double[float](), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_http_cache")),
    )


def downgrade() -> None:
    op.drop_table("http_cache")
