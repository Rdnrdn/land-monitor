"""Store source torgi region code and rematch lots by region names."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409_fix_lot_region_matching_and_source_code"
down_revision = "20260409_add_regions_directory"
branch_labels = None
depends_on = None


REGION_NAME_MATCH_SQL = """
    (l.region_name IS NOT NULL AND lower(btrim(l.region_name)) = lower(r.name))
    OR (l.region IS NOT NULL AND lower(btrim(l.region)) = lower(r.name))
"""


def upgrade() -> None:
    op.add_column("lots", sa.Column("source_torgi_region_code", sa.Text(), nullable=True))

    op.execute(
        f"""
        UPDATE lots AS l
        SET source_torgi_region_code = r.torgi_region_code::text
        FROM regions AS r
        WHERE ({REGION_NAME_MATCH_SQL})
          AND l.source_torgi_region_code IS NULL
        """
    )

    op.execute(
        f"""
        UPDATE lots AS l
        SET region_id = r.id
        FROM regions AS r
        WHERE ({REGION_NAME_MATCH_SQL})
          AND l.region_id IS DISTINCT FROM r.id
        """
    )

    op.execute(
        f"""
        UPDATE lots AS l
        SET region_id = NULL
        WHERE l.region_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM regions AS r
            WHERE {REGION_NAME_MATCH_SQL}
          )
        """
    )


def downgrade() -> None:
    op.drop_column("lots", "source_torgi_region_code")
