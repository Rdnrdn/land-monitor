"""Debug two specific noticeNumber responses."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from django.core.management.base import BaseCommand


NOTICE_URL = "https://torgi.gov.ru/new/api/public/notices/noticeNumber/{noticeNumber}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

NOTICE_NUMBERS = [
    "21000005710000001078",
    "21000006870000000477",
]


def _classify(json_parse_ok: bool, json_data: Any) -> str:
    if not json_parse_ok:
        return "non_json"
    if isinstance(json_data, dict):
        return "ok_dict" if json_data else "empty_dict"
    return "non_json"


class Command(BaseCommand):
    help = "Debug two specific noticeNumber responses."

    def handle(self, *args, **options):
        session = requests.Session()
        artifacts_dir = Path("/opt/land-monitor/artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_path = artifacts_dir / f"notice_two_cases_debug_{ts}.json"
        report_rows: list[dict[str, Any]] = []

        for notice_number in NOTICE_NUMBERS:
            url = NOTICE_URL.format(noticeNumber=notice_number)
            row: dict[str, Any] = {
                "noticeNumber": notice_number,
                "request_url": url,
            }
            try:
                resp = session.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
                row["http_status"] = resp.status_code
                row["final_url"] = resp.url
                row["content_type"] = resp.headers.get("Content-Type")
                text = resp.text or ""
                row["response_text_length"] = len(text)
                row["response_text_head_1000"] = text[:1000]
                row["response_text_tail_1000"] = text[-1000:] if len(text) > 1000 else text

                raw_path = artifacts_dir / f"notice_{notice_number}_raw.txt"
                raw_path.write_text(text, encoding="utf-8")
                row["raw_text_path"] = str(raw_path)

                json_parse_ok = True
                try:
                    json_data = resp.json()
                except Exception:
                    json_parse_ok = False
                    json_data = None
                row["json_parse_ok"] = "yes" if json_parse_ok else "no"
                row["json_type"] = type(json_data).__name__ if json_parse_ok else None
                row["json_bool"] = bool(json_data) if json_parse_ok else False
                if isinstance(json_data, dict):
                    row["top_level_keys"] = list(json_data.keys())
                    lots = json_data.get("lots")
                    row["has_lots"] = isinstance(lots, list)
                    row["lots_count"] = len(lots) if isinstance(lots, list) else 0
                    attrs = json_data.get("attributes")
                    row["has_attributes"] = isinstance(attrs, list)
                else:
                    row["top_level_keys"] = None
                    row["has_lots"] = False
                    row["lots_count"] = 0
                    row["has_attributes"] = False

                row["short_classification"] = _classify(json_parse_ok, json_data)
            except Exception as exc:
                row["http_status"] = None
                row["final_url"] = None
                row["content_type"] = None
                row["response_text_length"] = 0
                row["response_text_head_1000"] = None
                row["response_text_tail_1000"] = None
                row["json_parse_ok"] = "no"
                row["json_type"] = None
                row["json_bool"] = False
                row["top_level_keys"] = None
                row["has_lots"] = False
                row["lots_count"] = 0
                row["has_attributes"] = False
                row["short_classification"] = "exception"
                row["error"] = str(exc)

            report_rows.append(row)

        report_path.write_text(json.dumps(report_rows, ensure_ascii=False, indent=2), encoding="utf-8")

        for row in report_rows:
            self.stdout.write(
                "noticeNumber={noticeNumber} http_status={http_status} json_type={json_type} "
                "json_bool={json_bool} top_level_keys={top_level_keys} lots_count={lots_count} "
                "classification={short_classification}".format(**row)
            )
        self.stdout.write(f"report_json={report_path}")
