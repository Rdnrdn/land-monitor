from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError

from land_monitor.db import SessionLocal
from land_monitor.models import Lot


LOTCARD_ENDPOINT_TEMPLATE = "https://torgi.gov.ru/new/api/public/lotcards/{lotcard_id}"
SOURCE = "opendata_notice"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _notice_and_lot_number_from_source_lot_id(
    source_lot_id: str,
    notice_number: str | None,
) -> tuple[str | None, str | None]:
    if notice_number:
        prefix = f"{notice_number}_"
        if source_lot_id.startswith(prefix):
            return notice_number, _clean_text(source_lot_id[len(prefix) :])
    if "_" not in source_lot_id:
        return notice_number, None
    parsed_notice_number, parsed_lot_number = source_lot_id.rsplit("_", 1)
    return _clean_text(notice_number or parsed_notice_number), _clean_text(parsed_lot_number)


def _merge_lotcard_raw_data(existing: Any, lotcard_payload: dict[str, Any]) -> dict[str, Any]:
    raw_data = dict(existing) if isinstance(existing, dict) else {}
    raw_data["lotcard"] = lotcard_payload
    return raw_data


class Command(BaseCommand):
    help = "On-demand enrich one local lot from torgi.gov.ru lotcard API."

    def add_arguments(self, parser):
        parser.add_argument(
            "source_lot_id",
            nargs="?",
            help="Lot source_lot_id, for example <notice_number>_<lotNumber>.",
        )
        parser.add_argument(
            "--id",
            dest="lot_id",
            type=int,
            help="Local lots.id. Alternative to source_lot_id.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=20.0,
            help="HTTP timeout in seconds. Default: 20.",
        )
        parser.add_argument(
            "--retries",
            type=int,
            default=1,
            help="HTTP attempts for this one lot only. Default: 1.",
        )
        parser.add_argument(
            "--retry-delay",
            type=float,
            default=3.0,
            help="Delay between retry attempts in seconds. Default: 3.",
        )

    def handle(self, *args, **options):
        source_lot_id = _clean_text(options.get("source_lot_id"))
        lot_id = options.get("lot_id")
        if not source_lot_id and lot_id is None:
            raise CommandError("Pass source_lot_id or --id.")
        if source_lot_id and lot_id is not None:
            raise CommandError("Pass either source_lot_id or --id, not both.")

        stats = {
            "lot_found": False,
            "api_called": False,
            "success": False,
            "failed": False,
            "enriched": False,
        }
        errors: list[str] = []
        db = SessionLocal()
        try:
            query = db.query(Lot)
            if lot_id is not None:
                lot = query.filter(Lot.id == lot_id).one_or_none()
            else:
                lot = query.filter(Lot.source == SOURCE, Lot.source_lot_id == source_lot_id).one_or_none()

            if lot is None:
                stats["failed"] = True
                errors.append("lot_not_found")
                self.stdout.write(f"lot_found={stats['lot_found']}")
                self.stdout.write(f"api_called={stats['api_called']}")
                self.stdout.write("success=false")
                self.stdout.write("failed=true")
                self.stdout.write(f"errors={json.dumps(errors, ensure_ascii=False)}")
                raise CommandError("Lot not found.")

            stats["lot_found"] = True
            if lot.source != SOURCE:
                raise CommandError(f"Lot id={lot.id} has source={lot.source!r}; expected {SOURCE!r}.")

            notice_number = _clean_text(lot.notice_number)
            lot_source_lot_id = _clean_text(lot.source_lot_id)
            if not lot_source_lot_id:
                raise CommandError(f"Lot id={lot.id} has empty source_lot_id.")

            notice_number, lot_number = _notice_and_lot_number_from_source_lot_id(
                lot_source_lot_id,
                notice_number,
            )
            if not notice_number or not lot_number:
                raise CommandError(
                    f"Cannot derive notice_number/lotNumber for lot id={lot.id} source_lot_id={lot_source_lot_id}."
                )

            lotcard_id = f"{notice_number}_{lot_number}"
            url = LOTCARD_ENDPOINT_TEMPLATE.format(lotcard_id=lotcard_id)
            self.stdout.write(f"lot_found=true")
            self.stdout.write(f"lot_id={lot.id}")
            self.stdout.write(f"source={lot.source}")
            self.stdout.write(f"source_lot_id={lot_source_lot_id}")
            self.stdout.write(f"notice_number={notice_number}")
            self.stdout.write(f"lotNumber={lot_number}")
            self.stdout.write(f"url={url}")

            attempts = max(1, int(options["retries"]))
            last_error: str | None = None
            response: requests.Response | None = None
            stats["api_called"] = True
            for attempt in range(1, attempts + 1):
                try:
                    response = requests.get(url, headers=HEADERS, timeout=float(options["timeout"]))
                    self.stdout.write(f"attempt={attempt} status_code={response.status_code}")
                    if response.status_code == 200:
                        break
                    last_error = f"http_{response.status_code}"
                except requests.exceptions.Timeout:
                    last_error = "timeout"
                    self.stdout.write(f"attempt={attempt} error=timeout")
                except requests.RequestException as exc:
                    last_error = f"request_error:{exc}"
                    self.stdout.write(f"attempt={attempt} error={exc}")

                if attempt < attempts:
                    time.sleep(float(options["retry_delay"]))

            if response is None or response.status_code != 200:
                db.rollback()
                stats["failed"] = True
                errors.append(last_error or "empty_response")
                self.stdout.write(f"api_called={stats['api_called']}")
                self.stdout.write("success=false")
                self.stdout.write("failed=true")
                self.stdout.write(f"error={last_error or 'empty_response'}")
                self.stdout.write(f"errors={json.dumps(errors, ensure_ascii=False)}")
                return

            payload_size = len(response.content or b"")
            content_type = response.headers.get("Content-Type")
            self.stdout.write(f"content_type={content_type}")
            self.stdout.write(f"payload_bytes={payload_size}")

            try:
                payload = response.json()
            except ValueError as exc:
                db.rollback()
                stats["failed"] = True
                errors.append(f"invalid_json:{exc}")
                self.stdout.write("success=false")
                self.stdout.write("failed=true")
                self.stdout.write(f"error=invalid_json:{exc}")
                self.stdout.write(f"errors={json.dumps(errors, ensure_ascii=False)}")
                return

            if not isinstance(payload, dict):
                db.rollback()
                stats["failed"] = True
                errors.append(f"unexpected_json_type:{type(payload).__name__}")
                self.stdout.write("success=false")
                self.stdout.write("failed=true")
                self.stdout.write(f"error=unexpected_json_type:{type(payload).__name__}")
                self.stdout.write(f"errors={json.dumps(errors, ensure_ascii=False)}")
                return

            now = datetime.now(timezone.utc)
            lot.raw_data = _merge_lotcard_raw_data(lot.raw_data, payload)
            lot.lotcard_enriched_at = now
            db.commit()

            stats["success"] = True
            stats["enriched"] = True
            preview = json.dumps(payload, ensure_ascii=False)[:300]
            self.stdout.write(f"api_called={stats['api_called']}")
            self.stdout.write("success=true")
            self.stdout.write("failed=false")
            self.stdout.write("enriched=true")
            self.stdout.write(f"errors={json.dumps(errors, ensure_ascii=False)}")
            self.stdout.write(f"lotcard_enriched_at={now.isoformat()}")
            self.stdout.write(f"payload_preview={preview}")
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
