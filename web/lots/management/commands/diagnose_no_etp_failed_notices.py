"""Collect a sample of lots where notice fetch failed."""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from django.core.management.base import BaseCommand


SEARCH_URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
NOTICE_URL = "https://torgi.gov.ru/new/api/public/notices/noticeNumber/{noticeNumber}"
PUBLIC_NOTICE_URL = "https://torgi.gov.ru/new/public/notices/view/{noticeNumber}"

SEARCH_PARAMS = {
    "dynSubjRF": "53",
    "catCode": "2",
    "lotStatus": "PUBLISHED,APPLICATIONS_SUBMISSION",
    "sort": "firstVersionPublicationDate,desc",
    "withFacets": "false",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _fetch_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any] | None = None,
    retries: int = 3,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, headers=HEADERS, timeout=20)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(1 + attempt)
    if last_exc:
        raise last_exc
    return None


def _is_empty_etp(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


class Command(BaseCommand):
    help = "Collect sample of lots with failed notice fetch."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--sample", type=int, default=10)

    def handle(self, *args, **options):
        limit = int(options["limit"])
        sample = int(options["sample"])
        session = requests.Session()

        lots: list[dict[str, Any]] = []
        page = 0
        size = 50
        while len(lots) < limit:
            params = dict(SEARCH_PARAMS)
            params["offset"] = page * size
            params["size"] = size
            try:
                payload = _fetch_json(session, SEARCH_URL, params=params)
            except Exception:
                break
            content = payload.get("content") if isinstance(payload, dict) else []
            if not content:
                break
            for item in content:
                if not _is_empty_etp(item.get("etpCode")):
                    continue
                lots.append(item)
                if len(lots) >= limit:
                    break
            page += 1

        failed: list[dict[str, Any]] = []
        notice_cache: dict[str, dict[str, Any] | None] = {}

        for item in lots:
            source_lot_id = str(item.get("id"))
            notice_number = item.get("noticeNumber")
            notice_number_missing = not bool(notice_number)
            attempted_notice_url = (
                NOTICE_URL.format(noticeNumber=notice_number) if notice_number else None
            )
            public_notice_url = (
                PUBLIC_NOTICE_URL.format(noticeNumber=notice_number) if notice_number else None
            )
            status = "missing_notice_number" if notice_number_missing else None
            error = None
            short_error = None

            if notice_number:
                if notice_number in notice_cache:
                    notice = notice_cache[notice_number]
                else:
                    try:
                        notice = _fetch_json(session, attempted_notice_url, params=None)
                        notice_cache[notice_number] = notice
                    except Exception as exc:
                        notice = None
                        notice_cache[notice_number] = None
                        status = "error"
                        error = repr(exc)
                        short_error = str(exc)

                if notice is None and status is None:
                    status = "empty_notice"

            if status is not None:
                failed.append(
                    {
                        "source_lot_id": source_lot_id,
                        "title": item.get("lotName"),
                        "noticeNumber": notice_number,
                        "lot_url": f"https://torgi.gov.ru/new/public/lots/lot/{source_lot_id}",
                        "attempted_notice_url": attempted_notice_url,
                        "public_notice_url": public_notice_url,
                        "notice_fetch_status": status,
                        "notice_fetch_error": error,
                        "short_error_message": short_error,
                        "notice_number_missing": notice_number_missing,
                    }
                )
            if len(failed) >= sample:
                break

        artifacts_dir = Path("/opt/land-monitor/artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        json_path = artifacts_dir / f"no_etp_failed_notices_sample_{ts}.json"
        csv_path = artifacts_dir / f"no_etp_failed_notices_sample_{ts}.csv"

        with json_path.open("w", encoding="utf-8") as fp:
            json.dump(failed, fp, ensure_ascii=False, indent=2)

        with csv_path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(failed[0].keys()) if failed else [])
            if failed:
                writer.writeheader()
                writer.writerows(failed)

        self.stdout.write(f"report_json={json_path}")
        self.stdout.write(f"report_csv={csv_path}")
        self.stdout.write(f"failed_count={len(failed)}")
