"""Add application portal fields to notices."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_add_notice_application_portal"
down_revision = "20260407_add_notices_and_lot_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notices", sa.Column("application_portal_url", sa.Text(), nullable=True))
    op.add_column("notices", sa.Column("application_portal_domain", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notices", "application_portal_domain")
    op.drop_column("notices", "application_portal_url")
