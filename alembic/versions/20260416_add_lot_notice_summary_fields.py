"""Add lot notice summary fields.

Revision ID: 20260416_add_lot_notice_summary_fields
Revises: 20260415_add_regions_subject_rf_code
Create Date: 2026-04-16 11:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260416_add_lot_notice_summary_fields"
down_revision = "20260415_add_regions_subject_rf_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lots", sa.Column("notice_publish_date", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("lots", sa.Column("notice_url", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("application_start_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("lots", sa.Column("application_address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lots", "application_address")
    op.drop_column("lots", "application_start_at")
    op.drop_column("lots", "notice_url")
    op.drop_column("lots", "notice_publish_date")
