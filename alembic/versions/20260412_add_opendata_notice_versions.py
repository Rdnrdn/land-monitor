"""Add open data notice versions ledger."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_add_opendata_notice_versions"
down_revision = "20260412_add_subjects_directory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opendata_notice_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reg_num", sa.Text(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("publish_date", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("href", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("downloaded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "reg_num",
            "document_type",
            "publish_date",
            "href",
            name="uq_opendata_notice_versions_version",
        ),
    )
    op.create_index(
        "idx_opendata_notice_versions_status",
        "opendata_notice_versions",
        ["status"],
    )
    op.create_index(
        "idx_opendata_notice_versions_reg_num",
        "opendata_notice_versions",
        ["reg_num"],
    )


def downgrade() -> None:
    op.drop_index("idx_opendata_notice_versions_reg_num", table_name="opendata_notice_versions")
    op.drop_index("idx_opendata_notice_versions_status", table_name="opendata_notice_versions")
    op.drop_table("opendata_notice_versions")
