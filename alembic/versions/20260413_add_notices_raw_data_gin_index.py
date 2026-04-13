"""Add GIN index on notices.raw_data for opendata lookups."""

from __future__ import annotations

from alembic import op


revision = "20260413_add_notices_raw_data_gin_index"
down_revision = "20260412_add_lotcard_enriched_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_notices_raw_data_gin",
        "notices",
        ["raw_data"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_notices_raw_data_gin", table_name="notices")
