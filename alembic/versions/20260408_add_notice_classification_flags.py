"""Add classification flags to notices."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_add_notice_classification_flags"
down_revision = "20260408_add_notice_application_portal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notices", sa.Column("is_pre_auction", sa.Boolean(), nullable=True))
    op.add_column("notices", sa.Column("is_39_18", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("notices", "is_39_18")
    op.drop_column("notices", "is_pre_auction")
