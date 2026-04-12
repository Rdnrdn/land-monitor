"""Add subjects directory from Torgi NSI."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_add_subjects_directory"
down_revision = "20260409_add_municipalities_directory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("okato", sa.String(length=20), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("uq_subjects_code", "subjects", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_subjects_code", table_name="subjects")
    op.drop_table("subjects")
