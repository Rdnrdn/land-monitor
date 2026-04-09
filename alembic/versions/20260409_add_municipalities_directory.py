"""Add municipalities directory and lot municipality reference."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409_add_municipalities_directory"
down_revision = "20260409_fix_lot_region_matching_and_source_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "municipalities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_municipalities_region_sort_order", "municipalities", ["region_id", "sort_order"])
    op.create_index(
        "uq_municipalities_region_normalized_name",
        "municipalities",
        ["region_id", "normalized_name"],
        unique=True,
    )
    op.create_index(
        "uq_municipalities_region_slug",
        "municipalities",
        ["region_id", "slug"],
        unique=True,
    )

    op.add_column("lots", sa.Column("municipality_id", sa.Integer(), nullable=True))
    op.create_index("idx_lots_municipality_id", "lots", ["municipality_id"])
    op.create_foreign_key(
        "fk_lots_municipality_id",
        "lots",
        "municipalities",
        ["municipality_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_lots_municipality_id", "lots", type_="foreignkey")
    op.drop_index("idx_lots_municipality_id", table_name="lots")
    op.drop_column("lots", "municipality_id")
    op.drop_index("uq_municipalities_region_slug", table_name="municipalities")
    op.drop_index("uq_municipalities_region_normalized_name", table_name="municipalities")
    op.drop_index("idx_municipalities_region_sort_order", table_name="municipalities")
    op.drop_table("municipalities")
