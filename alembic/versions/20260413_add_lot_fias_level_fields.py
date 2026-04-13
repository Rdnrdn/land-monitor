"""Add normalized FIAS level fields to lots.

Revision ID: 20260413_add_lot_fias_level_fields
Revises: 20260413_add_lot_source_notice_bidd_type_code
Create Date: 2026-04-13 15:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260413_add_lot_fias_level_fields"
down_revision = "20260413_add_lot_source_notice_bidd_type_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lots", sa.Column("fias_level_3_guid", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("fias_level_3_name", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("fias_level_5_guid", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("fias_level_5_name", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("fias_level_6_guid", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("fias_level_6_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lots", "fias_level_6_name")
    op.drop_column("lots", "fias_level_6_guid")
    op.drop_column("lots", "fias_level_5_name")
    op.drop_column("lots", "fias_level_5_guid")
    op.drop_column("lots", "fias_level_3_name")
    op.drop_column("lots", "fias_level_3_guid")
