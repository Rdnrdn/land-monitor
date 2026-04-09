"""Municipality directory helpers for lots."""

from __future__ import annotations

import re
import unicodedata

import sqlalchemy as sa
from sqlalchemy.orm import Session


def normalize_municipality_name(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = unicodedata.normalize("NFKC", value).strip()
    if not candidate:
        return None
    candidate = candidate.replace("Ё", "Е").replace("ё", "е")
    candidate = re.sub(r"\s+", " ", candidate)
    return candidate.lower()


def slugify_municipality_name(value: str) -> str:
    candidate = normalize_municipality_name(value) or ""
    candidate = re.sub(r"[^0-9a-zа-я]+", "-", candidate)
    candidate = re.sub(r"-{2,}", "-", candidate).strip("-")
    return candidate or "municipality"


NORMALIZED_NAME_SQL = """
    lower(
        regexp_replace(
            replace(replace(btrim({value}), 'Ё', 'Е'), 'ё', 'е'),
            '\\s+',
            ' ',
            'g'
        )
    )
"""

SLUG_SQL = """
    trim(
        both '-' from regexp_replace(
            regexp_replace(
                {normalized_name},
                '[^0-9a-zа-я]+',
                '-',
                'g'
            ),
            '-+',
            '-',
            'g'
        )
    )
"""


def sync_lot_municipality_refs(db: Session) -> tuple[int, int, int]:
    """Create municipality directory rows from lots and backfill lots.municipality_id."""

    normalized_name_sql = NORMALIZED_NAME_SQL.format(value="l.municipality_name")
    slug_sql = SLUG_SQL.format(normalized_name="normalized_name")

    inserted_result = db.execute(
        sa.text(
            f"""
            WITH ranked AS (
                SELECT
                    l.region_id,
                    btrim(l.municipality_name) AS name,
                    {normalized_name_sql} AS normalized_name,
                    count(*) AS hits,
                    row_number() OVER (
                        PARTITION BY l.region_id, {normalized_name_sql}
                        ORDER BY count(*) DESC, length(btrim(l.municipality_name)) ASC, btrim(l.municipality_name) ASC
                    ) AS row_num
                FROM lots AS l
                WHERE l.region_id IS NOT NULL
                  AND l.municipality_name IS NOT NULL
                  AND btrim(l.municipality_name) <> ''
                GROUP BY l.region_id, btrim(l.municipality_name), {normalized_name_sql}
            )
            INSERT INTO municipalities (
                region_id,
                name,
                normalized_name,
                slug,
                is_active,
                sort_order
            )
            SELECT
                region_id,
                name,
                normalized_name,
                {slug_sql},
                true,
                0
            FROM ranked
            WHERE row_num = 1
            ON CONFLICT (region_id, normalized_name) DO UPDATE
            SET name = EXCLUDED.name,
                slug = EXCLUDED.slug,
                is_active = true
            """
        )
    )

    matched_result = db.execute(
        sa.text(
            f"""
            UPDATE lots AS l
            SET municipality_id = m.id
            FROM municipalities AS m
            WHERE l.region_id = m.region_id
              AND l.region_id IS NOT NULL
              AND l.municipality_name IS NOT NULL
              AND btrim(l.municipality_name) <> ''
              AND {normalized_name_sql} = m.normalized_name
              AND l.municipality_id IS DISTINCT FROM m.id
            """
        )
    )

    cleared_result = db.execute(
        sa.text(
            f"""
            UPDATE lots AS l
            SET municipality_id = NULL
            WHERE l.municipality_id IS NOT NULL
              AND (
                l.region_id IS NULL
                OR l.municipality_name IS NULL
                OR btrim(l.municipality_name) = ''
                OR NOT EXISTS (
                    SELECT 1
                    FROM municipalities AS m
                    WHERE m.region_id = l.region_id
                      AND {normalized_name_sql} = m.normalized_name
                )
              )
            """
        )
    )

    return (
        inserted_result.rowcount or 0,
        matched_result.rowcount or 0,
        cleared_result.rowcount or 0,
    )
