"""Add lotcard enrichment timestamp to lots."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_add_lotcard_enriched_at"
down_revision = "20260412_add_lot_subject_and_ownership_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lots", sa.Column("lotcard_enriched_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("lots", "lotcard_enriched_at")
