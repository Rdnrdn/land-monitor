from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from land_monitor.db import SessionLocal
from land_monitor.models import Lot
from lots.opendata_fias import extract_fias_levels


SOURCE = "opendata_notice"
TARGET_BIDD_TYPE = "ZK"
TARGET_SUBJECT_CODE = "50"
FIAS_FIELD_NAMES = (
    "fias_level_3_guid",
    "fias_level_3_name",
    "fias_level_5_guid",
    "fias_level_5_name",
    "fias_level_6_guid",
    "fias_level_6_name",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _hierarchy_present(raw_data: Any) -> bool:
    opendata = _as_dict(_as_dict(raw_data).get("opendata"))
    estate_address_fias = _as_dict(opendata.get("estateAddressFIAS"))
    address_by_fias = _as_dict(estate_address_fias.get("addressByFIAS"))
    hierarchy_objects = address_by_fias.get("hierarchyObjects")
    return isinstance(hierarchy_objects, list) and bool(hierarchy_objects)


class Command(BaseCommand):
    help = "Backfill normalized FIAS level 3/5/6 fields for MO + ZK + opendata_notice lots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not write to the database. A diagnostic report is still written.",
        )
        parser.add_argument(
            "--limit-lots",
            type=int,
            required=True,
            help="Safety cap for lots processed. Required to avoid accidental full-table writes.",
        )
        parser.add_argument(
            "--report-path",
            default=None,
            help="Optional JSON report path. Defaults to .local/diagnostics/lot_fias_levels_backfill_<timestamp>.json.",
        )

    def handle(self, *args, **options):
        started_at = datetime.now(timezone.utc)
        dry_run = bool(options["dry_run"])
        limit_lots = int(options["limit_lots"])
        if limit_lots <= 0:
            raise CommandError("--limit-lots must be a positive integer.")

        stats: dict[str, Any] = {
            "lots_scanned": 0,
            "filled": 0,
            "updated": 0,
            "already_set": 0,
            "missing_hierarchy": 0,
            "missing_level_3": 0,
            "missing_level_5": 0,
            "missing_level_6": 0,
            "errors": 0,
            "examples": [],
            "problem_examples": [],
        }

        db = SessionLocal()
        try:
            lots = (
                db.query(Lot)
                .filter(
                    Lot.source == SOURCE,
                    Lot.source_notice_bidd_type_code == TARGET_BIDD_TYPE,
                    Lot.subject_rf_code == TARGET_SUBJECT_CODE,
                )
                .order_by(Lot.id)
                .limit(limit_lots)
                .all()
            )

            for lot in lots:
                stats["lots_scanned"] += 1
                try:
                    raw_data = _as_dict(lot.raw_data)
                    if not _hierarchy_present(raw_data):
                        stats["missing_hierarchy"] += 1
                        if len(stats["problem_examples"]) < 20:
                            stats["problem_examples"].append(
                                {
                                    "lot_id": lot.id,
                                    "source_lot_id": lot.source_lot_id,
                                    "reason": "missing_hierarchy",
                                }
                            )
                        continue

                    opendata = _as_dict(raw_data.get("opendata"))
                    extracted = extract_fias_levels(opendata.get("estateAddressFIAS"))

                    if not extracted.get("fias_level_3_guid"):
                        stats["missing_level_3"] += 1
                    if not extracted.get("fias_level_5_guid"):
                        stats["missing_level_5"] += 1
                    if not extracted.get("fias_level_6_guid"):
                        stats["missing_level_6"] += 1

                    current_values = {field: _clean_text(getattr(lot, field)) for field in FIAS_FIELD_NAMES}
                    normalized_extracted = {field: _clean_text(extracted.get(field)) for field in FIAS_FIELD_NAMES}
                    if current_values == normalized_extracted:
                        stats["already_set"] += 1
                        continue

                    had_existing_value = any(value for value in current_values.values())
                    changed_fields: list[str] = []
                    for field in FIAS_FIELD_NAMES:
                        new_value = normalized_extracted[field]
                        if not new_value:
                            continue
                        if current_values[field] == new_value:
                            continue
                        setattr(lot, field, new_value)
                        changed_fields.append(field)

                    if not changed_fields:
                        stats["already_set"] += 1
                        continue

                    lot.updated_at = started_at
                    action = "updated" if had_existing_value else "filled"
                    stats[action] += 1

                    if len(stats["examples"]) < 20:
                        stats["examples"].append(
                            {
                                "action": action,
                                "lot_id": lot.id,
                                "source_lot_id": lot.source_lot_id,
                                "changed_fields": changed_fields,
                                "values": {field: normalized_extracted[field] for field in changed_fields},
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    if len(stats["problem_examples"]) < 20:
                        stats["problem_examples"].append(
                            {
                                "lot_id": lot.id,
                                "source_lot_id": lot.source_lot_id,
                                "reason": type(exc).__name__,
                                "error": str(exc),
                            }
                        )

            if dry_run:
                db.rollback()
            else:
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        stats["started_at"] = started_at.isoformat()
        stats["dry_run"] = dry_run
        stats["limit_lots"] = limit_lots

        report_path = Path(
            options["report_path"]
            or f".local/diagnostics/lot_fias_levels_backfill_{started_at:%Y%m%d_%H%M%S}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

        for key in (
            "lots_scanned",
            "filled",
            "updated",
            "already_set",
            "missing_hierarchy",
            "missing_level_3",
            "missing_level_5",
            "missing_level_6",
            "errors",
        ):
            self.stdout.write(f"{key}={stats[key]}")
        self.stdout.write(f"examples={json.dumps(stats['examples'][:10], ensure_ascii=False)}")
        self.stdout.write(f"problem_examples={json.dumps(stats['problem_examples'][:10], ensure_ascii=False)}")
        self.stdout.write(f"dry_run={dry_run}")
        self.stdout.write(f"report_path={report_path}")
