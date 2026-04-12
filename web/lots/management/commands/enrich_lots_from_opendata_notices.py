from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from land_monitor.db import SessionLocal
from land_monitor.models import Lot, Notice


LOT_SNAPSHOT_KEYS = (
    "lotNumber",
    "lotStatus",
    "lotName",
    "lotDescription",
    "biddingObjectInfo",
    "additionalDetails",
    "docs",
    "imageIds",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_nested(mapping: dict[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _compact_notice_subset(notice_payload: dict[str, Any], source_meta: dict[str, Any]) -> dict[str, Any]:
    common_info = _as_dict(notice_payload.get("commonInfo"))
    return {
        "noticeNumber": common_info.get("noticeNumber") or source_meta.get("regNum"),
        "publishDate": common_info.get("publishDate") or source_meta.get("publishDate"),
        "publicNoticeUrl": common_info.get("href"),
        "biddConditions": notice_payload.get("biddConditions"),
        "bidderOrg": notice_payload.get("bidderOrg"),
        "rightHolderInfo": notice_payload.get("rightHolderInfo"),
        "opendata_meta": source_meta,
    }


def _compact_lot_snapshot(lot_payload: dict[str, Any]) -> dict[str, Any]:
    bidding_object = _as_dict(lot_payload.get("biddingObjectInfo"))
    snapshot = {
        key: lot_payload.get(key)
        for key in LOT_SNAPSHOT_KEYS
        if lot_payload.get(key) is not None
    }

    extracted = {
        "estateAddress": lot_payload.get("estateAddress") or bidding_object.get("estateAddress"),
        "estateAddressFIAS": lot_payload.get("estateAddressFIAS") or bidding_object.get("estateAddressFIAS"),
        "subjectRF": lot_payload.get("subjectRF") or bidding_object.get("subjectRF"),
        "category": lot_payload.get("category") or bidding_object.get("category"),
        "ownershipForms": lot_payload.get("ownershipForms") or bidding_object.get("ownershipForms"),
        "characteristics": lot_payload.get("characteristics") or bidding_object.get("characteristics"),
    }
    snapshot.update({key: value for key, value in extracted.items() if value is not None})
    return snapshot


def _fias_guid(estate_address_fias: Any) -> str | None:
    if not isinstance(estate_address_fias, dict):
        return None
    return _clean_text(_get_nested(estate_address_fias, "addressByFIAS", "guid"))


def _dict_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return _clean_text(value.get("name"))


def _dict_code(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return _clean_text(value.get("code"))


def _fill_if_empty(lot: Lot, field: str, value: Any, changed_fields: set[str]) -> None:
    cleaned = _clean_text(value)
    if cleaned and not _clean_text(getattr(lot, field)):
        setattr(lot, field, cleaned)
        changed_fields.add(field)


def _merge_lot_raw_data(
    existing: Any,
    *,
    lot_snapshot: dict[str, Any],
    notice_subset: dict[str, Any],
) -> dict[str, Any]:
    raw_data = dict(existing) if isinstance(existing, dict) else {}
    raw_data["opendata"] = lot_snapshot
    raw_data["opendata_notice"] = notice_subset
    return raw_data


class Command(BaseCommand):
    help = "Enrich existing lots from already stored notices.raw_data['opendata'] notice.lots[]."

    def add_arguments(self, parser):
        parser.add_argument(
            "--report-path",
            default=None,
            help="Optional JSON report path. Defaults to .local/diagnostics/opendata_lot_enrichment_<timestamp>.json.",
        )
        parser.add_argument(
            "--limit-notices",
            type=int,
            default=0,
            help="Optional safety cap for notices processed. 0 means no cap.",
        )

    def handle(self, *args, **options):
        started_at = datetime.now(timezone.utc)
        db = SessionLocal()
        notices_seen = 0
        notices_with_opendata = 0
        notices_with_lots = 0
        total_lot_objects = 0
        source_lot_ids_built = 0
        matched = 0
        enriched = 0
        unmatched = 0
        already_same = 0
        updated_field_counts: dict[str, int] = {}
        matched_examples: list[dict[str, Any]] = []
        unmatched_examples: list[dict[str, Any]] = []
        limit_notices = int(options["limit_notices"])

        try:
            query = (
                db.query(Notice)
                .filter(Notice.raw_data["opendata"].isnot(None))
                .order_by(Notice.notice_number)
            )
            if limit_notices > 0:
                query = query.limit(limit_notices)

            for notice_row in query.yield_per(50):
                notices_seen += 1
                raw_data = _as_dict(notice_row.raw_data)
                opendata = _as_dict(raw_data.get("opendata"))
                if not opendata:
                    continue

                notices_with_opendata += 1
                notice_payload = _as_dict(
                    _get_nested(opendata, "exportObject", "structuredObject", "notice")
                )
                lots_payload = notice_payload.get("lots")
                if not isinstance(lots_payload, list) or not lots_payload:
                    continue

                notices_with_lots += 1
                source_meta = _as_dict(raw_data.get("opendata_meta"))
                notice_number = _clean_text(notice_row.notice_number) or _clean_text(
                    _get_nested(notice_payload, "commonInfo", "noticeNumber")
                )
                notice_subset = _compact_notice_subset(notice_payload, source_meta)

                for lot_payload in lots_payload:
                    if not isinstance(lot_payload, dict):
                        continue

                    total_lot_objects += 1
                    lot_number = _clean_text(lot_payload.get("lotNumber"))
                    if not notice_number or not lot_number:
                        if len(unmatched_examples) < 20:
                            unmatched_examples.append(
                                {
                                    "notice_number": notice_number,
                                    "lotNumber": lot_number,
                                    "source_lot_id": None,
                                    "reason": "missing_notice_number_or_lotNumber",
                                }
                            )
                        unmatched += 1
                        continue

                    source_lot_id = f"{notice_number}_{lot_number}"
                    source_lot_ids_built += 1
                    lot = db.query(Lot).filter(Lot.source_lot_id == source_lot_id).one_or_none()
                    if lot is None:
                        unmatched += 1
                        if len(unmatched_examples) < 20:
                            unmatched_examples.append(
                                {
                                    "notice_number": notice_number,
                                    "lotNumber": lot_number,
                                    "source_lot_id": source_lot_id,
                                    "reason": "lot_not_found",
                                }
                            )
                        continue

                    matched += 1
                    lot_snapshot = _compact_lot_snapshot(lot_payload)
                    new_raw_data = _merge_lot_raw_data(
                        lot.raw_data,
                        lot_snapshot=lot_snapshot,
                        notice_subset=notice_subset,
                    )

                    changed_fields: set[str] = set()
                    _fill_if_empty(lot, "title", lot_snapshot.get("lotName"), changed_fields)
                    _fill_if_empty(lot, "description", lot_snapshot.get("lotDescription"), changed_fields)
                    _fill_if_empty(lot, "address", lot_snapshot.get("estateAddress"), changed_fields)
                    _fill_if_empty(lot, "fias_guid", _fias_guid(lot_snapshot.get("estateAddressFIAS")), changed_fields)
                    _fill_if_empty(lot, "subject_rf_code", _dict_code(lot_snapshot.get("subjectRF")), changed_fields)
                    _fill_if_empty(lot, "category", _dict_name(lot_snapshot.get("category")), changed_fields)
                    _fill_if_empty(lot, "lot_status_external", lot_snapshot.get("lotStatus"), changed_fields)

                    raw_changed = new_raw_data != lot.raw_data
                    if raw_changed:
                        lot.raw_data = new_raw_data
                    if raw_changed or changed_fields:
                        lot.updated_at = started_at
                        enriched += 1
                        for field in changed_fields:
                            updated_field_counts[field] = updated_field_counts.get(field, 0) + 1
                    else:
                        already_same += 1

                    if len(matched_examples) < 5:
                        matched_examples.append(
                            {
                                "notice_number": notice_number,
                                "lotNumber": lot_number,
                                "source_lot_id": source_lot_id,
                                "matched_lot_id": lot.id,
                            }
                        )

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        report_path = Path(
            options["report_path"]
            or f".local/diagnostics/opendata_lot_enrichment_{started_at:%Y%m%d_%H%M%S}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "started_at": started_at.isoformat(),
            "notices_seen": notices_seen,
            "notices_with_opendata": notices_with_opendata,
            "notices_with_lots": notices_with_lots,
            "total_lot_objects": total_lot_objects,
            "source_lot_ids_built": source_lot_ids_built,
            "matched": matched,
            "enriched": enriched,
            "already_same": already_same,
            "unmatched": unmatched,
            "updated_field_counts": updated_field_counts,
            "matched_examples": matched_examples,
            "unmatched_examples": unmatched_examples,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(f"notices_seen={notices_seen}")
        self.stdout.write(f"notices_with_opendata={notices_with_opendata}")
        self.stdout.write(f"notices_with_lots={notices_with_lots}")
        self.stdout.write(f"total_lot_objects={total_lot_objects}")
        self.stdout.write(f"source_lot_ids_built={source_lot_ids_built}")
        self.stdout.write(f"matched={matched}")
        self.stdout.write(f"enriched={enriched}")
        self.stdout.write(f"already_same={already_same}")
        self.stdout.write(f"unmatched={unmatched}")
        self.stdout.write(f"matched_examples={json.dumps(matched_examples, ensure_ascii=False)}")
        self.stdout.write(f"unmatched_examples={json.dumps(unmatched_examples[:5], ensure_ascii=False)}")
        self.stdout.write(f"updated_field_counts={json.dumps(updated_field_counts, ensure_ascii=False)}")
        self.stdout.write(f"report_path={report_path}")
