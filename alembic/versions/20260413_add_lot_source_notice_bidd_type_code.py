"""Add normalized notice bidd type code to lots.

Revision ID: 20260413_add_lot_source_notice_bidd_type_code
Revises: 20260413_add_notices_opendata_publish_sort_index
Create Date: 2026-04-13 13:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260413_add_lot_source_notice_bidd_type_code"
down_revision = "20260413_add_notices_opendata_publish_sort_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lots",
        sa.Column("source_notice_bidd_type_code", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lots", "source_notice_bidd_type_code")
