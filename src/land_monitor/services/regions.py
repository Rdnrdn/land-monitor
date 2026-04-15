"""Region directory helpers for lots."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from land_monitor.models import Region


REGION_NAME_MATCH_SQL = """
    (l.region_name IS NOT NULL AND lower(btrim(l.region_name)) = lower(r.name))
    OR (l.region IS NOT NULL AND lower(btrim(l.region)) = lower(r.name))
"""


REGION_SEED_DATA: tuple[dict[str, object], ...] = (
    {
        "name": "Москва",
        "slug": "moskva",
        "torgi_region_code": 78,
        "subject_rf_code": "77",
        "is_active": True,
        "sort_order": 10,
    },
    {
        "name": "Московская область",
        "slug": "moskovskaya-oblast",
        "torgi_region_code": 53,
        "subject_rf_code": "50",
        "is_active": True,
        "sort_order": 20,
    },
    {
        "name": "Тульская область",
        "slug": "tulskaya-oblast",
        "torgi_region_code": 73,
        "subject_rf_code": "71",
        "is_active": True,
        "sort_order": 30,
    },
    {
        "name": "Калужская область",
        "slug": "kaluzhskaya-oblast",
        "torgi_region_code": 44,
        "subject_rf_code": "40",
        "is_active": True,
        "sort_order": 40,
    },
    {
        "name": "Ленинградская область",
        "slug": "leningradskaya-oblast",
        "torgi_region_code": 50,
        "subject_rf_code": "47",
        "is_active": True,
        "sort_order": 50,
    },
)


def list_active_regions(db: Session) -> list[Region]:
    return (
        db.query(Region)
        .filter(Region.is_active.is_(True))
        .order_by(Region.sort_order.asc(), Region.name.asc())
        .all()
    )


def sync_lot_region_refs(db: Session) -> tuple[int, int]:
    """Backfill lots.region_id from the region directory using region names only."""

    matched_result = db.execute(
        sa.text(
            f"""
            UPDATE lots AS l
            SET region_id = r.id
            FROM regions AS r
            WHERE ({REGION_NAME_MATCH_SQL})
              AND l.region_id IS DISTINCT FROM r.id
            """
        )
    )

    cleared_result = db.execute(
        sa.text(
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
    )

    return matched_result.rowcount or 0, cleared_result.rowcount or 0
