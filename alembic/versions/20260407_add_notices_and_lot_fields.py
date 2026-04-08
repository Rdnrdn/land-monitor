"""Add notices table and extend lots."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260407_add_notices_and_lot_fields"
down_revision = "20260407_lots_user_lots_refactor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("notice_number", sa.Text(), primary_key=True),
        sa.Column("notice_status", sa.Text()),
        sa.Column("publish_date", sa.TIMESTAMP(timezone=True)),
        sa.Column("create_date", sa.TIMESTAMP(timezone=True)),
        sa.Column("update_date", sa.TIMESTAMP(timezone=True)),
        sa.Column("bidd_type_code", sa.Text()),
        sa.Column("bidd_form_code", sa.Text()),
        sa.Column("bidder_org_name", sa.Text()),
        sa.Column("right_holder_name", sa.Text()),
        sa.Column("auction_site_url", sa.Text()),
        sa.Column("auction_site_domain", sa.Text()),
        sa.Column("auction_is_electronic", sa.Boolean()),
        sa.Column("detected_site_type", sa.Text()),
        sa.Column("detected_platform_code", sa.Text()),
        sa.Column("is_offline", sa.Boolean()),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("idx_notices_notice_number", "notices", ["notice_number"], unique=True)
    op.create_index("idx_notices_auction_site_domain", "notices", ["auction_site_domain"])

    op.add_column("lots", sa.Column("notice_number", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("region_name", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("subject_rf_code", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("application_end_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("lots", sa.Column("auction_start_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("lots", sa.Column("is_without_etp", sa.Boolean(), nullable=True))

    op.create_index("idx_lots_notice_number", "lots", ["notice_number"])
    op.create_index("idx_lots_region_name", "lots", ["region_name"])
    op.create_index("idx_lots_application_end_at", "lots", ["application_end_at"])

    op.create_foreign_key(
        "fk_lots_notice_number",
        "lots",
        "notices",
        ["notice_number"],
        ["notice_number"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_lots_notice_number", "lots", type_="foreignkey")
    op.drop_index("idx_lots_application_end_at", table_name="lots")
    op.drop_index("idx_lots_region_name", table_name="lots")
    op.drop_index("idx_lots_notice_number", table_name="lots")
    op.drop_column("lots", "is_without_etp")
    op.drop_column("lots", "auction_start_at")
    op.drop_column("lots", "application_end_at")
    op.drop_column("lots", "subject_rf_code")
    op.drop_column("lots", "region_name")
    op.drop_column("lots", "notice_number")
    op.drop_index("idx_notices_auction_site_domain", table_name="notices")
    op.drop_index("idx_notices_notice_number", table_name="notices")
    op.drop_table("notices")
