"""Analyze no-ETP lots using local DB as source."""

from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from django.core.management.base import BaseCommand
from sqlalchemy import or_

from land_monitor.db import SessionLocal
from land_monitor.models import Lot


NOTICE_URL = "https://torgi.gov.ru/new/api/public/notices/noticeNumber/{noticeNumber}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)

DOMAIN_RULES = {
    "rts-tender.ru": "ETP_RTS",
    "rts-tender.com": "ETP_RTS",
    "roseltorg.ru": "ETP_ROSELTORG",
    "sberbank-ast.ru": "ETP_SBERBANK_AST",
    "etp.gpb.ru": "ETP_GPB",
    "fabrikant.ru": "ETP_FABRIKANT",
    "tektorg.ru": "ETP_TEKTORG",
    "lot-online.ru": "ETP_LOT_ONLINE",
}

KEYWORD_RULES = {
    "р т с": "ETP_RTS",
    "р тс": "ETP_RTS",
    "rts tender": "ETP_RTS",
    "росэлторг": "ETP_ROSELTORG",
    "roseltorg": "ETP_ROSELTORG",
    "сбербанк-аст": "ETP_SBERBANK_AST",
    "sberbank-ast": "ETP_SBERBANK_AST",
    "гпб": "ETP_GPB",
    "etp.gpb": "ETP_GPB",
    "фабрикант": "ETP_FABRIKANT",
    "fabrikant": "ETP_FABRIKANT",
    "тэк-торг": "ETP_TEKTORG",
    "tektorg": "ETP_TEKTORG",
    "лот-онлайн": "ETP_LOT_ONLINE",
    "lot-online": "ETP_LOT_ONLINE",
}

OFFLINE_MARKERS = [
    "неэлектрон",
    "бумажн",
    "на бумажном носителе",
    "очно",
    "офлайн",
]


def _extract_all_strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    strings: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, sub in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            strings.extend(_extract_all_strings(sub, next_path))
    elif isinstance(value, list):
        for idx, sub in enumerate(value):
            next_path = f"{path}[{idx}]"
            strings.extend(_extract_all_strings(sub, next_path))
    elif isinstance(value, str):
        strings.append((value, path))
    return strings


def _extract_urls_from_strings(strings: list[tuple[str, str]]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for text, path in strings:
        for match in URL_RE.findall(text):
            found.append((match.rstrip(").,;"), path))
    return found


def _domain_from_url(url: str) -> str | None:
    try:
        host = urlparse(url).netloc.lower()
        return host.replace("www.", "")
    except Exception:
        return None


def _detect_platform_from_urls(urls: list[tuple[str, str]]) -> tuple[str | None, str | None, str | None, str | None]:
    for url, path in urls:
        domain = _domain_from_url(url)
        if not domain:
            continue
        for rule_domain, platform in DOMAIN_RULES.items():
            if domain == rule_domain or domain.endswith(f".{rule_domain}"):
                return platform, "KNOWN_ETP", domain, path
        if domain == "torgi.gov.ru" or domain.endswith(".torgi.gov.ru"):
            return None, "TORGI_PORTAL_REFERENCE", domain, path
        if domain.endswith(".gov.ru") or domain.endswith(".mosreg.ru") or domain.endswith(".tularegion.ru"):
            return None, "EXTERNAL_GOV_SITE", domain, path
        return None, "EXTERNAL_COMMERCIAL_SITE", domain, path
    return None, None, None, None


def _detect_platform_from_text(strings: list[tuple[str, str]]) -> tuple[str | None, str | None, str | None, str | None]:
    for text, path in strings:
        lowered = text.lower()
        if "torgi.gov.ru" in lowered:
            return None, "TORGI_PORTAL_REFERENCE", "torgi.gov.ru", path
        for marker in OFFLINE_MARKERS:
            if marker in lowered:
                return None, "OFFLINE", marker, path
        for keyword, platform in KEYWORD_RULES.items():
            if keyword in lowered:
                return platform, "KNOWN_ETP", keyword, path
    return None, None, None, None


def _fetch_notice(
    session: requests.Session,
    url: str,
    *,
    retry_count: int,
    timeout: int,
    backoff: list[float],
    delay: float,
) -> tuple[dict[str, Any] | None, str]:
    for attempt in range(retry_count):
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
            if response.status_code == 503:
                if attempt < retry_count - 1:
                    time.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                return None, "NOTICE_FETCH_HTTP_503"
            response.raise_for_status()
            try:
                data = response.json()
            except Exception:
                return None, "NOTICE_FETCH_INVALID_JSON"
            if not data:
                return None, "NOTICE_FETCH_EMPTY_JSON"
            return data if isinstance(data, dict) else None, "NOTICE_FETCH_OK"
        except requests.exceptions.Timeout:
            if attempt < retry_count - 1:
                time.sleep(backoff[min(attempt, len(backoff) - 1)])
                continue
            return None, "NOTICE_FETCH_TIMEOUT"
        except Exception:
            return None, "NOTICE_FETCH_INVALID_JSON"
        finally:
            if delay > 0:
                time.sleep(delay)
    return None, "NOTICE_FETCH_INVALID_JSON"


class Command(BaseCommand):
    help = "Analyze no-ETP lots using DB as source."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--notice-delay", type=float, default=1.5)
        parser.add_argument("--retry-count", type=int, default=3)

    def handle(self, *args, **options):
        limit = int(options["limit"])
        notice_delay = float(options["notice_delay"])
        retry_count = int(options["retry_count"])
        backoff = [3.0, 7.0, 15.0]

        db = SessionLocal()
        try:
            lots_db = (
                db.query(Lot)
                .filter(Lot.source == "torgi")
                .filter(or_(Lot.etp_code.is_(None), Lot.etp_code == ""))
                .filter(or_(Lot.region == "Московская область", Lot.region.ilike("Московская область%")))
                .limit(limit)
                .all()
            )
        finally:
            db.close()

        session = requests.Session()
        report_rows: list[dict[str, Any]] = []
        domain_counter: Counter[str] = Counter()
        keyword_counter: Counter[str] = Counter()
        notice_cache: dict[str, dict[str, Any] | None] = {}
        notices_downloaded = 0

        for lot in lots_db:
            raw = lot.raw_data or {}
            notice_number = raw.get("noticeNumber")
            notice_url = NOTICE_URL.format(noticeNumber=notice_number) if notice_number else None

            notice = None
            notice_fetch_status = "NOTICE_FETCH_INVALID_JSON"
            if notice_number:
                if notice_number in notice_cache:
                    notice = notice_cache[notice_number]
                    notice_fetch_status = "NOTICE_FETCH_OK" if notice else "NOTICE_FETCH_EMPTY_JSON"
                else:
                    notice, notice_fetch_status = _fetch_notice(
                        session,
                        notice_url,
                        retry_count=retry_count,
                        timeout=20,
                        backoff=backoff,
                        delay=notice_delay,
                    )
                    if notice_fetch_status == "NOTICE_FETCH_OK":
                        notices_downloaded += 1
                    notice_cache[notice_number] = notice
            else:
                notice_fetch_status = "NOTICE_FETCH_INVALID_JSON"

            strings: list[tuple[str, str]] = []
            urls: list[tuple[str, str]] = []
            string_map: dict[str, str] = {}
            if isinstance(notice, dict):
                strings = _extract_all_strings(notice)
                urls = _extract_urls_from_strings(strings)
                string_map = {path: text for text, path in strings if path}

            platform, site_type, matched, matched_path = _detect_platform_from_urls(urls)
            if matched and site_type:
                domain_counter[matched] += 1

            if site_type is None and notice_fetch_status == "NOTICE_FETCH_OK":
                platform, site_type, matched, matched_path = _detect_platform_from_text(strings)
                if matched and site_type:
                    keyword_counter[matched] += 1

            if site_type is None:
                if notice_fetch_status == "NOTICE_FETCH_OK":
                    site_type = "UNKNOWN"
                else:
                    site_type = notice_fetch_status
                matched = None
                matched_path = None
                platform = None

            matched_text_fragment = None
            if matched_path and matched_path in string_map:
                matched_text_fragment = string_map[matched_path][:200]

            report_rows.append(
                {
                    "source_lot_id": lot.source_lot_id,
                    "noticeNumber": notice_number,
                    "title": lot.title,
                    "region": lot.region,
                    "etp_code_original": lot.etp_code,
                    "detected_platform_code": platform,
                    "detected_site_type": site_type,
                    "detected_domain": matched if site_type in {"KNOWN_ETP", "EXTERNAL_GOV_SITE", "EXTERNAL_COMMERCIAL_SITE", "TORGI_PORTAL_REFERENCE"} else None,
                    "detection_method": "url_domain" if site_type in {"KNOWN_ETP", "EXTERNAL_GOV_SITE", "EXTERNAL_COMMERCIAL_SITE", "TORGI_PORTAL_REFERENCE"} else "notice_text" if site_type in {"OFFLINE", "KNOWN_ETP"} else "unknown",
                    "matched_value": matched,
                    "matched_field_path": matched_path,
                    "matched_text_fragment": matched_text_fragment,
                    "confidence": "high" if site_type == "KNOWN_ETP" else "medium" if site_type in {"EXTERNAL_GOV_SITE", "EXTERNAL_COMMERCIAL_SITE", "TORGI_PORTAL_REFERENCE", "OFFLINE"} else "low",
                    "notice_url": notice_url,
                    "comment": None,
                }
            )

        counts = Counter(row["detected_site_type"] for row in report_rows)
        summary = {
            "total_lots_without_etp": len(lots_db),
            "notices_downloaded": notices_downloaded,
            "known_etp_count": counts.get("KNOWN_ETP", 0),
            "external_gov_site_count": counts.get("EXTERNAL_GOV_SITE", 0),
            "external_commercial_site_count": counts.get("EXTERNAL_COMMERCIAL_SITE", 0),
            "torgi_portal_reference_count": counts.get("TORGI_PORTAL_REFERENCE", 0),
            "offline_count": counts.get("OFFLINE", 0),
            "unknown_count": counts.get("UNKNOWN", 0),
            "notice_fetch_http_503_count": counts.get("NOTICE_FETCH_HTTP_503", 0),
            "notice_fetch_timeout_count": counts.get("NOTICE_FETCH_TIMEOUT", 0),
            "notice_fetch_empty_json_count": counts.get("NOTICE_FETCH_EMPTY_JSON", 0),
            "notice_fetch_invalid_json_count": counts.get("NOTICE_FETCH_INVALID_JSON", 0),
            "top_domains": domain_counter.most_common(10),
            "top_keywords": keyword_counter.most_common(10),
        }

        artifacts_dir = Path("/opt/land-monitor/artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        json_path = artifacts_dir / f"no_etp_from_db_{ts}.json"
        csv_path = artifacts_dir / f"no_etp_from_db_{ts}.csv"

        with json_path.open("w", encoding="utf-8") as fp:
            json.dump({"summary": summary, "rows": report_rows}, fp, ensure_ascii=False, indent=2)

        with csv_path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(report_rows[0].keys()) if report_rows else [])
            if report_rows:
                writer.writeheader()
                writer.writerows(report_rows)

        self.stdout.write(f"report_json={json_path}")
        self.stdout.write(f"report_csv={csv_path}")
        self.stdout.write(f"summary_total={summary['total_lots_without_etp']}")
        self.stdout.write(f"summary_notices={summary['notices_downloaded']}")
