"""Import initial lots from torgi.gov.ru into lots table."""

from __future__ import annotations

import time
from typing import Any

import requests
from django.core.management.base import BaseCommand
from sqlalchemy import select, tuple_

from land_monitor.db import SessionLocal
from land_monitor.models import Lot
from land_monitor.services.lot_normalizer import normalize_lot
from land_monitor.services.sync_lots import bulk_upsert_lots, deduplicate_lots


API_URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
BASE_PARAMS = {
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


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name") or value.get("code") or str(value)
    if isinstance(value, list):
        return str(value)
    return str(value)


def _sanitize_lot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text_fields = {
        "title",
        "description",
        "region",
        "district",
        "address",
        "fias_guid",
        "cadastre_number",
        "category",
        "permitted_use",
        "currency_code",
        "etp_code",
        "etp_name",
        "organizer_name",
        "organizer_inn",
        "organizer_kpp",
        "lot_status_external",
        "price_bucket",
        "segment",
        "source_url",
    }
    cleaned = dict(payload)
    for key in text_fields:
        if key in cleaned:
            cleaned[key] = _coerce_text(cleaned[key])
    return cleaned


def _fetch_page(session: requests.Session, page: int, size: int, retries: int = 3) -> list[dict[str, Any]]:
    params = dict(BASE_PARAMS)
    params["offset"] = page * size
    params["size"] = size
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(API_URL, params=params, headers=HEADERS, timeout=20)
            response.raise_for_status()
            payload = response.json()
            content = payload.get("content") if isinstance(payload, dict) else []
            return content if isinstance(content, list) else []
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(1 + attempt)
    if last_exc:
        raise last_exc
    return []


class Command(BaseCommand):
    help = "Import first N lots from torgi.gov.ru into lots table."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--page-size", type=int, default=10)

    def handle(self, *args, **options):
        limit = int(options["limit"])
        page_size = int(options["page_size"])

        session = requests.Session()
        collected: list[dict[str, Any]] = []
        page = 0
        errors = 0

        while len(collected) < limit:
            items = _fetch_page(session, page=page, size=page_size)
            if not items:
                break
            collected.extend(items)
            if len(collected) >= limit:
                collected = collected[:limit]
                break
            page += 1

        normalized: list[dict[str, Any]] = []
        for item in collected:
            try:
                normalized.append(_sanitize_lot_payload(normalize_lot(item, source="torgi")))
            except Exception:
                errors += 1

        deduped = deduplicate_lots(normalized)
        if not deduped:
            self.stdout.write(
                f"received={len(collected)} created=0 updated=0 errors={errors}"
            )
            return

        keys = [(item["source"], item["source_lot_id"]) for item in deduped]
        db = SessionLocal()
        try:
            existing_keys = set(
                db.execute(
                    select(Lot.source, Lot.source_lot_id).where(
                        tuple_(Lot.source, Lot.source_lot_id).in_(keys)
                    )
                ).all()
            )
            upserted_ids = bulk_upsert_lots(db, deduped)
            db.commit()
            created_count = sum(1 for key in keys if key not in existing_keys)
            updated_count = max(len(upserted_ids) - created_count, 0)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        self.stdout.write(
            f"received={len(collected)} created={created_count} updated={updated_count} errors={errors}"
        )
