"""Reparse notices from stored raw_data and update url fields."""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from django.core.management.base import BaseCommand
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from land_monitor.db import SessionLocal
from land_monitor.models import Notice

URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


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


def _upsert_notice(db, values: dict[str, Any]) -> None:
    stmt = insert(Notice).values(**values)
    update_cols = {
        "auction_site_url": stmt.excluded.auction_site_url,
        "auction_site_domain": stmt.excluded.auction_site_domain,
        "application_portal_url": stmt.excluded.application_portal_url,
        "application_portal_domain": stmt.excluded.application_portal_domain,
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[Notice.notice_number],
        set_=update_cols,
    )
    db.execute(stmt)


class Command(BaseCommand):
    help = "Reparse stored notices and update portal/auction urls."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        batch_size = int(options["batch_size"])
        total_processed = 0
        auction_site_url_found = 0
        application_portal_url_found = 0

        db = SessionLocal()
        try:
            while True:
                rows = (
                    db.query(Notice)
                    .filter(Notice.raw_data.isnot(None))
                    .order_by(Notice.notice_number.asc())
                    .limit(batch_size)
                    .offset(total_processed)
                    .all()
                )
                if not rows:
                    break
                for notice_row in rows:
                    raw = notice_row.raw_data or {}
                    attributes = raw.get("attributes")
                    etp_url = _extract_etp_url_from_attributes(attributes)
                    application_portal_url = _extract_application_portal_url_from_attributes(attributes)

                    if etp_url:
                        auction_site_url_found += 1
                    if application_portal_url:
                        application_portal_url_found += 1

                    values = {
                        "notice_number": notice_row.notice_number,
                        "auction_site_url": etp_url,
                        "auction_site_domain": _domain_from_url(etp_url),
                        "application_portal_url": application_portal_url,
                        "application_portal_domain": _domain_from_url(application_portal_url),
                    }
                    _upsert_notice(db, values)
                    total_processed += 1
                db.commit()
        finally:
            db.close()

        self.stdout.write(f"total_processed={total_processed}")
        self.stdout.write(f"auction_site_url_found={auction_site_url_found}")
        self.stdout.write(f"application_portal_url_found={application_portal_url_found}")
