from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from land_monitor.db import SessionLocal
from land_monitor.models import Lot, Notice


SOURCE = "opendata_notice"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _notice_bidd_type_code(raw_data: Any) -> str | None:
    raw = _as_dict(raw_data)
    opendata = _as_dict(raw.get("opendata"))
    export_object = _as_dict(opendata.get("exportObject"))
    structured_object = _as_dict(export_object.get("structuredObject"))
    notice = _as_dict(structured_object.get("notice"))
    common_info = _as_dict(notice.get("commonInfo"))
    bidd_type = _as_dict(common_info.get("biddType"))
    return _clean_text(bidd_type.get("code"))


class Command(BaseCommand):
    help = "Backfill lots.source_notice_bidd_type_code from parent notices.raw_data['opendata']."

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
            help="Optional JSON report path. Defaults to .local/diagnostics/lot_notice_bidd_type_backfill_<timestamp>.json.",
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
            "missing_notice": 0,
            "missing_bidd_type_code": 0,
            "errors": 0,
            "examples": [],
            "problem_examples": [],
        }

        db = SessionLocal()
        try:
            lots = (
                db.query(Lot)
                .filter(Lot.source == SOURCE)
                .order_by(Lot.id)
                .limit(limit_lots)
                .all()
            )
            notice_numbers = sorted(
                {
                    notice_number
                    for notice_number in (lot.notice_number for lot in lots)
                    if notice_number
                }
            )
            notices_by_number = {
                notice.notice_number: notice
                for notice in db.query(Notice).filter(Notice.notice_number.in_(notice_numbers)).all()
            }

            for lot in lots:
                stats["lots_scanned"] += 1
                try:
                    if not lot.notice_number:
                        stats["missing_notice"] += 1
                        if len(stats["problem_examples"]) < 20:
                            stats["problem_examples"].append(
                                {
                                    "lot_id": lot.id,
                                    "source_lot_id": lot.source_lot_id,
                                    "reason": "missing_notice_number",
                                }
                            )
                        continue

                    notice = notices_by_number.get(lot.notice_number)
                    if notice is None:
                        stats["missing_notice"] += 1
                        if len(stats["problem_examples"]) < 20:
                            stats["problem_examples"].append(
                                {
                                    "lot_id": lot.id,
                                    "source_lot_id": lot.source_lot_id,
                                    "notice_number": lot.notice_number,
                                    "reason": "missing_parent_notice",
                                }
                            )
                        continue

                    bidd_type_code = _notice_bidd_type_code(notice.raw_data)
                    if not bidd_type_code:
                        stats["missing_bidd_type_code"] += 1
                        if len(stats["problem_examples"]) < 20:
                            stats["problem_examples"].append(
                                {
                                    "lot_id": lot.id,
                                    "source_lot_id": lot.source_lot_id,
                                    "notice_number": lot.notice_number,
                                    "reason": "missing_bidd_type_code",
                                }
                            )
                        continue

                    current_value = _clean_text(lot.source_notice_bidd_type_code)
                    if current_value == bidd_type_code:
                        stats["already_set"] += 1
                        continue

                    lot.source_notice_bidd_type_code = bidd_type_code
                    lot.updated_at = started_at
                    action = "filled" if not current_value else "updated"
                    stats[action] += 1

                    if len(stats["examples"]) < 20:
                        stats["examples"].append(
                            {
                                "action": action,
                                "lot_id": lot.id,
                                "source_lot_id": lot.source_lot_id,
                                "notice_number": lot.notice_number,
                                "from": current_value,
                                "to": bidd_type_code,
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    if len(stats["problem_examples"]) < 20:
                        stats["problem_examples"].append(
                            {
                                "lot_id": lot.id,
                                "source_lot_id": lot.source_lot_id,
                                "notice_number": lot.notice_number,
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
            or f".local/diagnostics/lot_notice_bidd_type_backfill_{started_at:%Y%m%d_%H%M%S}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

        for key in (
            "lots_scanned",
            "filled",
            "updated",
            "already_set",
            "missing_notice",
            "missing_bidd_type_code",
            "errors",
        ):
            self.stdout.write(f"{key}={stats[key]}")
        self.stdout.write(f"examples={json.dumps(stats['examples'][:10], ensure_ascii=False)}")
        self.stdout.write(f"problem_examples={json.dumps(stats['problem_examples'][:10], ensure_ascii=False)}")
        self.stdout.write(f"dry_run={dry_run}")
        self.stdout.write(f"report_path={report_path}")
