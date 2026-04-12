"""Add lot subject and ownership fields for open data mapping."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_add_lot_subject_and_ownership_fields"
down_revision = "20260412_add_opendata_notice_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lots", sa.Column("subject_id", sa.Integer(), nullable=True))
    op.add_column("lots", sa.Column("ownership_form_code", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("ownership_form_name", sa.Text(), nullable=True))
    op.create_index("idx_lots_subject_id", "lots", ["subject_id"])
    op.create_foreign_key(
        "fk_lots_subject_id",
        "lots",
        "subjects",
        ["subject_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_lots_subject_id", "lots", type_="foreignkey")
    op.drop_index("idx_lots_subject_id", table_name="lots")
    op.drop_column("lots", "ownership_form_name")
    op.drop_column("lots", "ownership_form_code")
    op.drop_column("lots", "subject_id")
