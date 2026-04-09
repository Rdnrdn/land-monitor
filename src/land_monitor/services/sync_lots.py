"""Batch sync pipeline for lots."""

from __future__ import annotations

from typing import Any, Iterable

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from land_monitor.models import Lot
from land_monitor.services.municipalities import sync_lot_municipality_refs
from land_monitor.services.lot_normalizer import normalize_lot
from land_monitor.services.regions import sync_lot_region_refs


def deduplicate_lots(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (item["source"], item["source_lot_id"])
        dedup[key] = item
    return list(dedup.values())


def bulk_upsert_lots(db: Session, items: list[dict[str, Any]]) -> list[int]:
    if not items:
        return []
    insert_stmt = insert(Lot).values(items)
    excluded_names = {"id", "created_at", "updated_at"}
    update_columns = {
        col.name: insert_stmt.excluded[col.name]
        for col in Lot.__table__.columns
        if col.name not in excluded_names
    }
    update_columns["updated_at"] = sa.text("NOW()")
    compare_columns = [col for col in Lot.__table__.columns if col.name not in excluded_names]
    change_detect = sa.or_(
        *[col.is_distinct_from(insert_stmt.excluded[col.name]) for col in compare_columns]
    )
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["source", "source_lot_id"],
        set_=update_columns,
        where=change_detect,
    ).returning(Lot.id)
    result = db.execute(stmt).scalars().all()
    return result


def mark_missing_lots_inactive(
    db: Session,
    *,
    source: str,
    present_keys: Iterable[tuple[str, str]],
    skip_finished: bool = True,
) -> int:
    keys = list(present_keys)
    stmt = sa.update(Lot).where(Lot.source == source)
    if keys:
        stmt = stmt.where(sa.tuple_(Lot.source, Lot.source_lot_id).not_in(keys))
    stmt = stmt.where(Lot.is_active.is_distinct_from(sa.false()))
    if skip_finished:
        stmt = stmt.where(sa.or_(Lot.is_finished.is_(False), Lot.is_finished.is_(None)))
    stmt = stmt.values(is_active=False, updated_at=sa.text("NOW()"))
    result = db.execute(stmt)
    return result.rowcount or 0


def sync_lots(
    db: Session,
    raw_items: list[dict[str, Any]],
    *,
    source: str = "torgi",
    mark_missing_inactive: bool = False,
    skip_finished: bool = True,
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    invalid_items: list[dict[str, Any]] = []
    invalid_count = 0
    invalid_limit = 20
    for idx, item in enumerate(raw_items):
        try:
            normalized.append(normalize_lot(item, source=source))
        except Exception as exc:
            invalid_count += 1
            if len(invalid_items) < invalid_limit:
                source_lot_id = None
                if isinstance(item, dict):
                    source_lot_id = (
                        item.get("id")
                        or item.get("lotId")
                        or item.get("lotNumber")
                        or item.get("noticeNumber")
                    )
                invalid_items.append(
                    {
                        "index": idx,
                        "error": str(exc),
                        "source_lot_id": str(source_lot_id) if source_lot_id is not None else None,
                    }
                )
    deduped = deduplicate_lots(normalized)
    upserted_ids: list[int] = []
    marked_inactive = 0
    unchanged_count = 0
    deactivation_skipped = False
    deactivation_skip_reason: str | None = None
    with db.begin():
        if deduped:
            upserted_ids = bulk_upsert_lots(db, deduped)
            sync_lot_region_refs(db)
            sync_lot_municipality_refs(db)
        if mark_missing_inactive:
            if not deduped:
                deactivation_skipped = True
                deactivation_skip_reason = "no_valid_items"
            elif invalid_count > 0:
                deactivation_skipped = True
                deactivation_skip_reason = "invalid_items_present"
            else:
                keys = [(item["source"], item["source_lot_id"]) for item in deduped]
                marked_inactive = mark_missing_lots_inactive(
                    db,
                    source=source,
                    present_keys=keys,
                    skip_finished=skip_finished,
                )
    if deduped:
        unchanged_count = max(len(deduped) - len(upserted_ids), 0)

    return {
        "normalized_count": len(normalized),
        "deduped_count": len(deduped),
        "upserted_count": len(upserted_ids),
        "unchanged_count": unchanged_count,
        "marked_inactive": marked_inactive,
        "invalid_count": invalid_count,
        "invalid_items": invalid_items,
        "deactivation_skipped": deactivation_skipped,
        "deactivation_skip_reason": deactivation_skip_reason,
    }
