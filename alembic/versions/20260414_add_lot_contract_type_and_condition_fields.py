"""Add contract type and deal-condition text fields to lots.

Revision ID: 20260414_add_lot_contract_type_and_condition_fields
Revises: 20260413_add_lot_fias_level_fields
Create Date: 2026-04-14 07:25:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260414_add_lot_contract_type_and_condition_fields"
down_revision = "20260413_add_lot_fias_level_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lots", sa.Column("contract_type_bucket", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("contract_type_source_code", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("contract_type_source_name", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("land_restrictions_text", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("contract_sign_period_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lots", "contract_sign_period_text")
    op.drop_column("lots", "land_restrictions_text")
    op.drop_column("lots", "contract_type_source_name")
    op.drop_column("lots", "contract_type_source_code")
    op.drop_column("lots", "contract_type_bucket")
