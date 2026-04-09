"""Add regions directory and lot region reference."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409_add_regions_directory"
down_revision = "20260408_add_lot_location_fields"
branch_labels = None
depends_on = None


REGION_ROWS = (
    {
        "id": 1,
        "name": "Москва",
        "slug": "moskva",
        "torgi_region_code": 78,
        "is_active": True,
        "sort_order": 10,
    },
    {
        "id": 2,
        "name": "Московская область",
        "slug": "moskovskaya-oblast",
        "torgi_region_code": 53,
        "is_active": True,
        "sort_order": 20,
    },
    {
        "id": 3,
        "name": "Тульская область",
        "slug": "tulskaya-oblast",
        "torgi_region_code": 73,
        "is_active": True,
        "sort_order": 30,
    },
    {
        "id": 4,
        "name": "Калужская область",
        "slug": "kaluzhskaya-oblast",
        "torgi_region_code": 44,
        "is_active": True,
        "sort_order": 40,
    },
    {
        "id": 5,
        "name": "Ленинградская область",
        "slug": "leningradskaya-oblast",
        "torgi_region_code": 50,
        "is_active": True,
        "sort_order": 50,
    },
)


def upgrade() -> None:
    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("torgi_region_code", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("idx_regions_sort_order", "regions", ["sort_order"])
    op.create_index("uq_regions_slug", "regions", ["slug"], unique=True)
    op.create_index("uq_regions_torgi_region_code", "regions", ["torgi_region_code"], unique=True)

    regions_table = sa.table(
        "regions",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String(length=255)),
        sa.column("slug", sa.String(length=100)),
        sa.column("torgi_region_code", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(regions_table, list(REGION_ROWS))

    op.add_column("lots", sa.Column("region_id", sa.Integer(), nullable=True))
    op.create_index("idx_lots_region_id", "lots", ["region_id"])
    op.create_foreign_key(
        "fk_lots_region_id",
        "lots",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE lots AS l
        SET region_id = r.id
        FROM regions AS r
        WHERE (
            (l.subject_rf_code IS NOT NULL AND btrim(l.subject_rf_code) = r.torgi_region_code::text)
            OR (l.region_name IS NOT NULL AND lower(btrim(l.region_name)) = lower(r.name))
            OR (l.region IS NOT NULL AND lower(btrim(l.region)) = lower(r.name))
        )
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_lots_region_id", "lots", type_="foreignkey")
    op.drop_index("idx_lots_region_id", table_name="lots")
    op.drop_column("lots", "region_id")
    op.drop_index("uq_regions_torgi_region_code", table_name="regions")
    op.drop_index("uq_regions_slug", table_name="regions")
    op.drop_index("idx_regions_sort_order", table_name="regions")
    op.drop_table("regions")
