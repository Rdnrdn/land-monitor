"""Reclassify notices based on stored raw_data."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from land_monitor.db import SessionLocal
from land_monitor.models import Notice


def _extract_strings(value: Any) -> list[str]:
    strings: list[str] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            strings.append(current)
            continue
        if isinstance(current, dict):
            stack.extend(current.values())
            continue
        if isinstance(current, list):
            stack.extend(current)
            continue
    return strings


def _detect_is_39_18(text: str) -> bool:
    return "39.18" in text.lower()


def _detect_is_pre_auction(text: str) -> bool:
    t = text.lower()
    return "намерени" in t and "участв" in t


class Command(BaseCommand):
    help = "Reclassify notices from raw_data."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        batch_size = int(options["batch_size"])
        total_processed = 0
        is_pre_auction_count = 0
        is_39_18_count = 0

        db = SessionLocal()
        try:
            offset = 0
            while True:
                rows = (
                    db.query(Notice)
                    .filter(Notice.raw_data.isnot(None))
                    .order_by(Notice.notice_number.asc())
                    .limit(batch_size)
                    .offset(offset)
                    .all()
                )
                if not rows:
                    break

                for notice in rows:
                    raw = notice.raw_data
                    if not isinstance(raw, (dict, list)):
                        total_processed += 1
                        continue
                    all_strings = _extract_strings(raw)
                    text_blob = " ".join(all_strings)

                    is_39_18 = _detect_is_39_18(text_blob)
                    is_pre_auction = is_39_18 or _detect_is_pre_auction(text_blob)

                    notice.is_39_18 = is_39_18
                    notice.is_pre_auction = is_pre_auction

                    if is_39_18:
                        is_39_18_count += 1
                    if is_pre_auction:
                        is_pre_auction_count += 1

                    total_processed += 1

                db.commit()
                offset += batch_size
        finally:
            db.close()

        self.stdout.write(f"total_processed={total_processed}")
        self.stdout.write(f"is_pre_auction_count={is_pre_auction_count}")
        self.stdout.write(f"is_39_18_count={is_39_18_count}")
