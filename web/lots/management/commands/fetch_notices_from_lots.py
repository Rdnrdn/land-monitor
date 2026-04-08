"""Fetch notices for lots and store in notices table."""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests
from django.core.management.base import BaseCommand
from sqlalchemy import or_, text
from sqlalchemy.dialects.postgresql import insert

from land_monitor.db import SessionLocal
from land_monitor.models import Lot, Notice


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
DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    return None


ATTRIBUTE_CODE_WHITELIST = {
    "DA_biddingPlace_BA(229)",
    "DA_biddingProcedure_BA(229)",
    "DA_officialSite_BA(229)",
}

ATTRIBUTE_NAME_HINTS = (
    "место проведения торгов",
    "электронная площадка",
    "официальный сайт",
)

APPLICATION_NAME_HINTS = (
    "адрес и способ подачи заявлений",
    "подача заявлений",
    "подача заявок",
    "прием заявлений",
    "адрес подачи заявлений",
)

APPLICATION_VALUE_HINTS = (
    "рпгу",
    "госуслуг",
    "gosuslugi",
    "uslugi",
    "epgu",
)


def _normalize_url(value: str) -> str:
    return value.rstrip(").,;")


def _url_from_text(text: str) -> str | None:
    match = URL_RE.search(text)
    if match:
        return _normalize_url(match.group(0))
    domain_match = DOMAIN_RE.search(text)
    if not domain_match:
        return None
    domain = domain_match.group(0)
    return f"https://{domain}"


def _attr_name_matches(attr: dict[str, Any]) -> bool:
    for key in ("fullName", "name", "title", "caption"):
        value = attr.get(key)
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        for hint in ATTRIBUTE_NAME_HINTS:
            if hint in lowered:
                return True
    return False


def _attr_name_matches_application(attr: dict[str, Any]) -> bool:
    for key in ("fullName", "name", "title", "caption"):
        value = attr.get(key)
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        for hint in APPLICATION_NAME_HINTS:
            if hint in lowered:
                return True
    return False


def _value_mentions_application(value: str) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in APPLICATION_VALUE_HINTS)


def _extract_etp_url_from_attributes(attributes: Any) -> str | None:
    if not isinstance(attributes, list):
        return None
    for attr in attributes:
        if not isinstance(attr, dict):
            continue
        code = attr.get("code")
        if code not in ATTRIBUTE_CODE_WHITELIST and not _attr_name_matches(attr):
            continue
        for key in ("value", "valueText", "text", "name"):
            value = attr.get(key)
            if not isinstance(value, str):
                continue
            found = _url_from_text(value)
            if found:
                return found
    return None


def _extract_application_portal_url_from_attributes(attributes: Any) -> str | None:
    if not isinstance(attributes, list):
        return None
    for attr in attributes:
        if not isinstance(attr, dict):
            continue
        if not _attr_name_matches_application(attr):
            for key in ("value", "valueText", "text", "name"):
                value = attr.get(key)
                if isinstance(value, str) and _value_mentions_application(value):
                    found = _url_from_text(value)
                    if found:
                        return found
            continue
        for key in ("value", "valueText", "text", "name"):
            value = attr.get(key)
            if not isinstance(value, str):
                continue
            found = _url_from_text(value)
            if found:
                return found
    return None


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
        return host.replace("www.", "") if host else None
    except Exception:
        return None


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


def _portal_reference_found(notice: dict[str, Any]) -> bool:
    for text in _extract_strings(notice):
        if "torgi.gov.ru" in text.lower():
            return True
    return False


def _is_offline_notice(notice: dict[str, Any]) -> bool:
    explicit = notice.get("isOffline")
    if isinstance(explicit, bool):
        return explicit
    for text in _extract_strings(notice):
        lowered = text.lower()
        if "неэлектрон" in lowered or "бумажн" in lowered or "очная" in lowered:
            return True
    return False


def _extract_notice_field(notice: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = notice.get(key)
        if value is not None:
            return str(value)
    return None


def _fetch_notice(
    session: requests.Session,
    url: str,
    *,
    retry_count: int,
    backoff: list[float],
    timeout: int,
) -> tuple[dict[str, Any] | None, str]:
    last_error: str = "error"
    for attempt in range(retry_count):
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
            if response.status_code == 503:
                last_error = "http_503"
                if attempt < retry_count - 1:
                    time.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                return None, "http_503"
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not data:
                return None, "empty_json"
            return data, "ok"
        except requests.exceptions.Timeout:
            last_error = "timeout"
            if attempt < retry_count - 1:
                time.sleep(backoff[min(attempt, len(backoff) - 1)])
                continue
            return None, "timeout"
        except Exception:
            last_error = "error"
            if attempt < retry_count - 1:
                time.sleep(backoff[min(attempt, len(backoff) - 1)])
                continue
            return None, "error"
    return None, last_error


def _upsert_notice(db, values: dict[str, Any]) -> None:
    stmt = insert(Notice).values(**values)
    update_cols = {
        "notice_status": stmt.excluded.notice_status,
        "publish_date": stmt.excluded.publish_date,
        "create_date": stmt.excluded.create_date,
        "update_date": stmt.excluded.update_date,
        "bidder_org_name": stmt.excluded.bidder_org_name,
        "right_holder_name": stmt.excluded.right_holder_name,
        "auction_site_url": stmt.excluded.auction_site_url,
        "auction_site_domain": stmt.excluded.auction_site_domain,
        "application_portal_url": stmt.excluded.application_portal_url,
        "application_portal_domain": stmt.excluded.application_portal_domain,
        "auction_is_electronic": stmt.excluded.auction_is_electronic,
        "is_offline": stmt.excluded.is_offline,
        "raw_data": stmt.excluded.raw_data,
        "fetched_at": stmt.excluded.fetched_at,
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[Notice.notice_number],
        set_=update_cols,
    )
    db.execute(stmt)


class Command(BaseCommand):
    help = "Fetch notices for lots and store into notices table."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--only-no-etp", action="store_true")
        parser.add_argument("--start-index", type=int, default=0)
        parser.add_argument("--max-items", type=int, default=50)

    def handle(self, *args, **options):
        limit = int(options["limit"])
        only_no_etp = bool(options["only_no_etp"])
        start_index = int(options["start_index"])
        max_items = int(options["max_items"])
        retry_count = 3
        backoff = [3.0, 7.0, 15.0]
        delay = 1.5
        timeout = 20

        db = SessionLocal()
        try:
            expected_fields = {
                "notice_number",
                "notice_status",
                "publish_date",
                "create_date",
                "update_date",
                "auction_start_date",
                "bidder_org_name",
                "right_holder_name",
                "auction_site_url",
                "auction_site_domain",
                "application_portal_url",
                "application_portal_domain",
                "auction_is_electronic",
                "is_offline",
                "portal_reference_found",
                "raw_data",
                "fetched_at",
            }
            model_fields = set(Notice.__table__.columns.keys())
            missing_in_model = sorted(expected_fields - model_fields)
            if missing_in_model:
                self.stdout.write(f"missing_in_model={missing_in_model}")

            db_fields = [
                row[0]
                for row in db.execute(
                    text(
                        "select column_name from information_schema.columns "
                        "where table_name = 'notices' order by ordinal_position"
                    )
                ).fetchall()
            ]
            missing_in_db = sorted(expected_fields - set(db_fields))
            if missing_in_db:
                self.stdout.write(f"missing_in_db={missing_in_db}")

            query = db.query(Lot.notice_number).filter(Lot.notice_number.isnot(None))
            if only_no_etp:
                query = query.filter(
                    or_(Lot.etp_code.is_(None), Lot.etp_code == "")
                )
                query = query.outerjoin(
                    Notice, Notice.notice_number == Lot.notice_number
                ).filter(
                    or_(Notice.raw_data.is_(None), Notice.fetched_at.is_(None))
                )
            query = query.distinct().offset(start_index)
            effective_limit = min(limit, max_items)
            notice_numbers = [row[0] for row in query.limit(effective_limit).all()]
        finally:
            db.close()

        session = requests.Session()
        downloaded = 0
        errors = 0
        http_503 = 0
        etp_url_found = 0
        application_portal_url_found = 0

        for notice_number in notice_numbers:
            if not notice_number:
                continue
            url = NOTICE_URL.format(noticeNumber=notice_number)
            notice, status = _fetch_notice(
                session,
                url,
                retry_count=retry_count,
                backoff=backoff,
                timeout=timeout,
            )
            if status == "http_503":
                http_503 += 1
            if status != "ok" or not notice:
                errors += 1
                time.sleep(delay)
                continue

            publish_date = _parse_dt(
                notice.get("publishDate") or notice.get("publishDateTime")
            )
            create_date = _parse_dt(
                notice.get("createDate") or notice.get("createDateTime")
            )
            update_date = _parse_dt(
                notice.get("updateDate") or notice.get("updateDateTime")
            )
            auction_start_date = _parse_dt(
                notice.get("auctionStartDate")
                or notice.get("biddingStartDate")
                or notice.get("auctionDate")
            )

            attributes = notice.get("attributes")
            etp_url = _extract_etp_url_from_attributes(attributes)
            if etp_url:
                etp_url_found += 1
            application_portal_url = _extract_application_portal_url_from_attributes(attributes)
            if application_portal_url:
                application_portal_url_found += 1
            portal_reference_found = _portal_reference_found(notice)
            auction_is_electronic = notice.get("auctionIsElectronic")
            if isinstance(auction_is_electronic, str):
                auction_is_electronic = auction_is_electronic.lower() == "true"
            if not isinstance(auction_is_electronic, bool):
                auction_is_electronic = None
            is_offline = _is_offline_notice(notice)

            values = {
                "notice_number": str(notice_number),
                "notice_status": notice.get("status") or notice.get("noticeStatus"),
                "publish_date": publish_date,
                "create_date": create_date,
                "update_date": update_date,
                "bidder_org_name": _extract_notice_field(
                    notice, ["bidderOrgName", "bidderOrganization", "bidderName"]
                ),
                "right_holder_name": _extract_notice_field(
                    notice, ["rightHolderName", "rightHolder", "ownerName"]
                ),
                "auction_site_url": etp_url,
                "auction_site_domain": _domain_from_url(etp_url),
                "application_portal_url": application_portal_url,
                "application_portal_domain": _domain_from_url(application_portal_url),
                "auction_is_electronic": auction_is_electronic,
                "is_offline": is_offline,
                "raw_data": notice,
                "fetched_at": datetime.utcnow(),
            }
            if auction_start_date:
                notice["auctionStartDateParsed"] = auction_start_date.isoformat()

            db_write = SessionLocal()
            try:
                _upsert_notice(db_write, values)
                db_write.commit()
                downloaded += 1
            except Exception as exc:
                db_write.rollback()
                errors += 1
                self.stdout.write(f"write_error_notice_number={notice_number}")
                self.stdout.write(f"write_error_type={type(exc).__name__}")
                self.stdout.write(f"write_error_text={exc}")
                self.stdout.write(f"write_error_keys={sorted(values.keys())}")
                raise SystemExit(1)
            finally:
                db_write.close()

            time.sleep(delay)

        self.stdout.write(f"notices_downloaded={downloaded}")
        self.stdout.write(f"errors={errors}")
        self.stdout.write(f"http_503={http_503}")
        self.stdout.write(f"etp_url_found={etp_url_found}")
        self.stdout.write(f"application_portal_url_found={application_portal_url_found}")
