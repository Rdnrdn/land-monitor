"""Add partial sort index for notices opendata listing."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260413_add_notices_opendata_publish_sort_index"
down_revision = "20260413_add_notices_raw_data_gin_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_notices_opendata_publish_sort",
        "notices",
        ["publish_date", "fetched_at", "notice_number"],
        postgresql_where=sa.text("raw_data ? 'opendata'"),
    )


def downgrade() -> None:
    op.drop_index("idx_notices_opendata_publish_sort", table_name="notices")
