"""Add subject RF code to regions.

Revision ID: 20260415_add_regions_subject_rf_code
Revises: 20260414_add_lot_contract_type_and_condition_fields
Create Date: 2026-04-15 11:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260415_add_regions_subject_rf_code"
down_revision = "20260414_add_lot_contract_type_and_condition_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("regions", sa.Column("subject_rf_code", sa.Text(), nullable=True))
    op.create_index("uq_regions_subject_rf_code", "regions", ["subject_rf_code"], unique=True)

    op.execute(
        """
        UPDATE regions
        SET subject_rf_code = CASE slug
            WHEN 'moskovskaya-oblast' THEN '50'
            WHEN 'moskva' THEN '77'
            WHEN 'tulskaya-oblast' THEN '71'
            WHEN 'kaluzhskaya-oblast' THEN '40'
            WHEN 'leningradskaya-oblast' THEN '47'
            ELSE subject_rf_code
        END
        """
    )

    op.execute(
        """
        UPDATE regions AS r
        SET subject_rf_code = s.code
        FROM subjects AS s
        WHERE r.subject_rf_code IS NULL
          AND lower(btrim(r.name)) = lower(btrim(s.name))
        """
    )


def downgrade() -> None:
    op.drop_index("uq_regions_subject_rf_code", table_name="regions")
    op.drop_column("regions", "subject_rf_code")
