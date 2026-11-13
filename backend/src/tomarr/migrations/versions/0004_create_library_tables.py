"""create library tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14 00:20:16.581553

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column(
            "format", sa.Enum("manga", "manhwa", "webtoon", native_enum=False), nullable=False
        ),
        sa.Column(
            "reading_direction",
            sa.Enum("rtl", "ltr", "vertical", native_enum=False),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_series")),
    )
    op.create_table(
        "alias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum(
                "mangabaka",
                "anilist",
                "mangadex",
                "mangaupdates",
                "rakuten",
                "ndl",
                "openbd",
                "webtoon",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"], ["series.id"], name=op.f("fk_alias_series_id_series"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alias")),
        sa.UniqueConstraint("series_id", "name", name=op.f("uq_alias_series_id")),
    )
    op.create_table(
        "chapter",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
            name=op.f("fk_chapter_series_id_series"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chapter")),
        sa.UniqueConstraint("series_id", "number", name=op.f("uq_chapter_series_id")),
    )
    op.create_table(
        "edition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
            name=op.f("fk_edition_series_id_series"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_edition")),
    )
    with op.batch_alter_table("edition", schema=None) as batch_op:
        batch_op.create_index(
            "uq_edition_primary_per_series",
            ["series_id"],
            unique=True,
            sqlite_where=sa.text("is_primary"),
        )

    op.create_table(
        "series_external_id",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum(
                "mangabaka",
                "anilist",
                "mangadex",
                "mangaupdates",
                "rakuten",
                "ndl",
                "openbd",
                "webtoon",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("value", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
            name=op.f("fk_series_external_id_series_id_series"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_series_external_id")),
        sa.UniqueConstraint("series_id", "provider", name=op.f("uq_series_external_id_series_id")),
    )
    with op.batch_alter_table("series_external_id", schema=None) as batch_op:
        batch_op.create_index(
            "ix_series_external_id_provider_value", ["provider", "value"], unique=False
        )

    op.create_table(
        "episode",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("chapter_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["chapter.id"],
            name=op.f("fk_episode_chapter_id_chapter"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
            name=op.f("fk_episode_series_id_series"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_episode")),
    )
    # Alembic cannot see an expression index, so this one is written by hand. It is created
    # without batch mode, because batch reflection warns that it cannot read the index.
    op.create_index(
        "uq_episode_series_season_number",
        "episode",
        ["series_id", sa.literal_column("coalesce(season, 0)"), "number"],
        unique=True,
    )

    op.create_table(
        "volume",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edition_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("isbn", sa.String(), nullable=True),
        sa.Column("cover_url", sa.String(), nullable=True),
        sa.Column("synopsis", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            ["edition.id"],
            name=op.f("fk_volume_edition_id_edition"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_volume")),
        sa.UniqueConstraint("edition_id", "number", name=op.f("uq_volume_edition_id")),
        sa.UniqueConstraint("id", "edition_id", name=op.f("uq_volume_id")),
    )
    op.create_table(
        "mapping",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edition_id", sa.Integer(), nullable=False),
        sa.Column("volume_id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Integer(), nullable=False),
        sa.Column(
            "provenance",
            sa.Enum(
                "user",
                "mangadex_aggregate",
                "description_parse",
                "llm_extraction",
                "inferred",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Enum("high", "medium", "low", native_enum=False), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["chapter.id"],
            name=op.f("fk_mapping_chapter_id_chapter"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            ["edition.id"],
            name=op.f("fk_mapping_edition_id_edition"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["volume_id", "edition_id"],
            ["volume.id", "volume.edition_id"],
            name=op.f("fk_mapping_volume_id_volume"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mapping")),
        sa.UniqueConstraint("edition_id", "chapter_id", name=op.f("uq_mapping_edition_id")),
    )
    op.create_table(
        "volume_external_id",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("volume_id", sa.Integer(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum(
                "mangabaka",
                "anilist",
                "mangadex",
                "mangaupdates",
                "rakuten",
                "ndl",
                "openbd",
                "webtoon",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("value", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["volume_id"],
            ["volume.id"],
            name=op.f("fk_volume_external_id_volume_id_volume"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_volume_external_id")),
        sa.UniqueConstraint("volume_id", "provider", name=op.f("uq_volume_external_id_volume_id")),
    )
    with op.batch_alter_table("volume_external_id", schema=None) as batch_op:
        batch_op.create_index(
            "ix_volume_external_id_provider_value", ["provider", "value"], unique=False
        )


def downgrade() -> None:
    # Dropping a table drops its indexes, so none are dropped one by one.
    op.drop_table("volume_external_id")
    op.drop_table("mapping")
    op.drop_table("volume")
    op.drop_table("episode")
    op.drop_table("series_external_id")
    op.drop_table("alias")
    op.drop_table("edition")
    op.drop_table("chapter")
    op.drop_table("series")
