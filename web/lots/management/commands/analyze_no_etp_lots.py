"""Analyze lots without ETP and infer platforms from notices."""

from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from django.core.management.base import BaseCommand


SEARCH_URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
NOTICE_URL = "https://torgi.gov.ru/new/api/public/notices/noticeNumber/{noticeNumber}"

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


def _fetch_search_page(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    *,
    retry_count: int,
    timeout: int,
    backoff: list[float],
) -> tuple[dict[str, Any] | None, str | None]:
    for attempt in range(retry_count):
        try:
            response = session.get(url, params=params, headers=HEADERS, timeout=timeout)
            if response.status_code == 503:
                if attempt < retry_count - 1:
                    time.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                return None, "http_503"
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else None, None
        except requests.exceptions.Timeout:
            if attempt < retry_count - 1:
                time.sleep(backoff[min(attempt, len(backoff) - 1)])
                continue
            return None, "timeout"
        except Exception as exc:
            return None, str(exc)
    return None, "unknown_error"


def _fetch_notice(
    session: requests.Session,
    url: str,
    *,
    retry_count: int,
    timeout: int,
    backoff: list[float],
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
    return None, "NOTICE_FETCH_INVALID_JSON"


def _is_empty_etp(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


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


class Command(BaseCommand):
    help = "Analyze lots without ETP and infer platform from notices."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--fast-debug", action="store_true")
        parser.add_argument("--search-delay", type=float, default=1.0)
        parser.add_argument("--notice-delay", type=float, default=0.7)
        parser.add_argument("--retry-count", type=int, default=3)

    def handle(self, *args, **options):
        limit = int(options["limit"])
        fast_debug = bool(options["fast_debug"])
        search_delay = float(options["search_delay"])
        notice_delay = float(options["notice_delay"])
        retry_count = int(options["retry_count"])
        if fast_debug:
            limit = 30
        session = requests.Session()

        lots: list[dict[str, Any]] = []
        page = 0
        size = 50
        max_pages = 50
        search_retries = retry_count
        search_timeout = 20
        notice_retries = retry_count
        notice_timeout = 20
        backoff = [2.0, 5.0, 10.0]
        if fast_debug:
            max_pages = 5
            search_retries = 1
            search_timeout = 8
            notice_retries = 1
            notice_timeout = 8
        search_pages_checked = 0
        search_total_seen = 0
        search_empty_etp_found = 0
        search_errors: list[dict[str, str]] = []
        search_had_empty_payload = False
        while len(lots) < limit and page < max_pages:
            params = dict(SEARCH_PARAMS)
            params["offset"] = page * size
            params["size"] = size
            payload, error = _fetch_search_page(
                session,
                SEARCH_URL,
                params,
                retry_count=search_retries,
                timeout=search_timeout,
                backoff=backoff,
            )
            if error:
                search_errors.append({"page": str(page), "error": error})
                self.stdout.write(f"page={page} status=error error={error}")
                page += 1
                time.sleep(search_delay)
                continue
            self.stdout.write(f"page={page} status=ok")
            content = payload.get("content") if isinstance(payload, dict) else []
            if not content:
                search_had_empty_payload = True
                break
            search_pages_checked += 1
            search_total_seen += len(content)
            for item in content:
                etp_code = item.get("etpCode")
                if not _is_empty_etp(etp_code):
                    continue
                search_empty_etp_found += 1
                lot = {
                    "source_lot_id": str(item.get("id")),
                    "noticeNumber": item.get("noticeNumber"),
                    "lotNumber": item.get("lotNumber"),
                    "title": item.get("lotName"),
                    "source_url": f"https://torgi.gov.ru/new/public/lots/lot/{item.get('id')}",
                    "region": item.get("region"),
                    "price_min": item.get("priceMin"),
                    "application_deadline": item.get("applicationDeadline"),
                    "auction_date": item.get("auctionDate"),
                    "etp_code": etp_code,
                    "raw_data": item,
                }
                lots.append(lot)
                if len(lots) >= limit:
                    break
            page += 1
            time.sleep(search_delay)

        notice_cache: dict[str, dict[str, Any] | None] = {}
        notices_downloaded = 0
        report_rows: list[dict[str, Any]] = []
        domain_counter: Counter[str] = Counter()
        keyword_counter: Counter[str] = Counter()
        unknown_diagnostics: list[dict[str, Any]] = []

        for lot in lots:
            notice_number = lot.get("noticeNumber")
            notice_url = None
            notice = None
            notice_fetch_status = "NOTICE_FETCH_OK"
            notice_fetch_error = None
            if notice_number:
                notice_url = NOTICE_URL.format(noticeNumber=notice_number)
                if notice_number in notice_cache:
                    notice = notice_cache[notice_number]
                else:
                    notice, notice_fetch_status = _fetch_notice(
                        session,
                        notice_url,
                        retry_count=notice_retries,
                        timeout=notice_timeout,
                        backoff=backoff,
                    )
                    if notice_fetch_status == "NOTICE_FETCH_OK":
                        notices_downloaded += 1
                        self.stdout.write(f"notice={notice_number} status=ok")
                    elif notice_fetch_status == "NOTICE_FETCH_HTTP_503":
                        notice_fetch_error = "http_503"
                        self.stdout.write(f"notice={notice_number} status=503")
                    elif notice_fetch_status == "NOTICE_FETCH_TIMEOUT":
                        notice_fetch_error = "timeout"
                        self.stdout.write(f"notice={notice_number} status=timeout")
                    else:
                        notice_fetch_error = "invalid_json"
                        self.stdout.write(f"notice={notice_number} status=invalid")
                    notice_cache[notice_number] = notice
                    time.sleep(notice_delay)
            else:
                notice_fetch_status = "NOTICE_FETCH_INVALID_JSON"

            urls: list[tuple[str, str]] = []
            strings: list[tuple[str, str]] = []
            string_map: dict[str, str] = {}
            if isinstance(notice, dict):
                strings = _extract_all_strings(notice)
                string_map = {path: text for text, path in strings if path}
                urls = _extract_urls_from_strings(strings)
            else:
                if notice_fetch_status == "NOTICE_FETCH_OK":
                    notice_fetch_status = "NOTICE_FETCH_EMPTY_JSON"

            platform, site_type, matched, matched_path = _detect_platform_from_urls(urls)
            if matched and site_type:
                domain_counter[matched] += 1

            if site_type is None:
                platform, site_type, matched, matched_path = _detect_platform_from_text(strings)
                if matched and site_type:
                    keyword_counter[matched] += 1

            if site_type is None:
                site_type = "UNKNOWN"
                matched = None
                matched_path = None
                platform = None

            confidence = "low"
            if site_type == "KNOWN_ETP" and matched:
                confidence = "high"
            elif site_type in {"EXTERNAL_GOV_SITE", "EXTERNAL_COMMERCIAL_SITE"} and matched:
                confidence = "medium"
            elif site_type in {"TORGI_PORTAL_REFERENCE", "OFFLINE"}:
                confidence = "medium"

            matched_text_fragment = None
            if matched_path and matched_path in string_map:
                matched_text_fragment = string_map[matched_path][:200]

            report_rows.append(
                {
                    "source_lot_id": lot.get("source_lot_id"),
                    "noticeNumber": notice_number,
                    "title": lot.get("title"),
                    "region": lot.get("region"),
                    "etp_code_original": lot.get("etp_code"),
                    "detected_platform_code": platform,
                    "detected_site_type": site_type,
                    "detected_domain": matched if site_type in {"KNOWN_ETP", "EXTERNAL_GOV_SITE", "EXTERNAL_COMMERCIAL_SITE", "TORGI_PORTAL_REFERENCE"} else None,
                    "detection_method": "url_domain" if site_type in {"KNOWN_ETP", "EXTERNAL_GOV_SITE", "EXTERNAL_COMMERCIAL_SITE", "TORGI_PORTAL_REFERENCE"} else "notice_text" if site_type in {"OFFLINE", "KNOWN_ETP"} else "unknown",
                    "matched_value": matched,
                    "matched_field_path": matched_path,
                    "matched_text_fragment": matched_text_fragment,
                    "confidence": confidence,
                    "notice_url": notice_url,
                    "comment": None,
                }
            )

            if site_type == "UNKNOWN" and len(unknown_diagnostics) < 20:
                notice_keys = list(notice.keys()) if isinstance(notice, dict) else []
                text_blob = " ".join(text for text, _ in strings)
                has_urls = bool(urls)
                keyword_hits = {
                    "электронн": "электронн" in text_blob.lower(),
                    "площадк": "площадк" in text_blob.lower(),
                    "сайт": "сайт" in text_blob.lower(),
                    "аукцион": "аукцион" in text_blob.lower(),
                    "торги": "торги" in text_blob.lower(),
                    "бумажн": "бумажн" in text_blob.lower(),
                }
                if notice_fetch_status in {"NOTICE_FETCH_HTTP_503", "NOTICE_FETCH_TIMEOUT", "NOTICE_FETCH_INVALID_JSON"}:
                    unknown_sub = "UNKNOWN_NOTICE_NOT_LOADED"
                elif notice_fetch_status == "NOTICE_FETCH_EMPTY_JSON":
                    unknown_sub = "UNKNOWN_NOTICE_EMPTY"
                elif not has_urls and not any(keyword_hits.values()):
                    unknown_sub = "UNKNOWN_NO_SIGNALS"
                else:
                    unknown_sub = "UNKNOWN_PARSE_WEAK"
                unknown_diagnostics.append(
                    {
                        "source_lot_id": lot.get("source_lot_id"),
                        "noticeNumber": notice_number,
                        "notice_fetch_status": notice_fetch_status,
                        "notice_loaded": notice_fetch_status == "ok" and isinstance(notice, dict),
                        "notice_keys": notice_keys,
                        "string_fields_count": len(strings),
                        "has_urls": has_urls,
                        "keyword_hits": keyword_hits,
                        "unknown_subcategory": unknown_sub,
                    }
                )

        artifacts_dir = Path("/opt/land-monitor/artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        json_path = artifacts_dir / f"no_etp_report_{ts}.json"
        csv_path = artifacts_dir / f"no_etp_report_{ts}.csv"

        counts = Counter(row["detected_site_type"] for row in report_rows)
        unknown_sub_counts = Counter(item["unknown_subcategory"] for item in unknown_diagnostics)
        summary = {
            "total_lots_without_etp": len(lots),
            "notices_downloaded": notices_downloaded,
            "known_etp_count": counts.get("KNOWN_ETP", 0),
            "external_gov_site_count": counts.get("EXTERNAL_GOV_SITE", 0),
            "external_commercial_site_count": counts.get("EXTERNAL_COMMERCIAL_SITE", 0),
            "torgi_portal_reference_count": counts.get("TORGI_PORTAL_REFERENCE", 0),
            "offline_count": counts.get("OFFLINE", 0),
            "unknown_count": counts.get("UNKNOWN", 0),
            "top_domains": domain_counter.most_common(10),
            "top_keywords": keyword_counter.most_common(10),
            "counts": counts,
            "search_pages_checked": search_pages_checked,
            "search_total_seen": search_total_seen,
            "search_empty_etp_found": search_empty_etp_found,
            "search_errors": search_errors,
            "search_errors_count": len(search_errors),
            "search_had_empty_payload": search_had_empty_payload,
            "unknown_notice_not_loaded_count": unknown_sub_counts.get("UNKNOWN_NOTICE_NOT_LOADED", 0),
            "unknown_notice_empty_count": unknown_sub_counts.get("UNKNOWN_NOTICE_EMPTY", 0),
            "unknown_no_signals_count": unknown_sub_counts.get("UNKNOWN_NO_SIGNALS", 0),
            "unknown_parse_weak_count": unknown_sub_counts.get("UNKNOWN_PARSE_WEAK", 0),
        }

        with json_path.open("w", encoding="utf-8") as fp:
            json.dump(
                {"summary": summary, "rows": report_rows, "unknown_diagnostics": unknown_diagnostics},
                fp,
                ensure_ascii=False,
                indent=2,
            )

        with csv_path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(report_rows[0].keys()) if report_rows else [])
            if report_rows:
                writer.writeheader()
                writer.writerows(report_rows)

        self.stdout.write(f"report_json={json_path}")
        self.stdout.write(f"report_csv={csv_path}")
        self.stdout.write(f"summary_total={summary['total_lots_without_etp']}")
        self.stdout.write(f"summary_known_etp={summary['known_etp_count']}")
        self.stdout.write(f"summary_notices={summary['notices_downloaded']}")
