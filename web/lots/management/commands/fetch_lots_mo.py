"""Fetch lots from torgi.gov.ru for Moscow region and upsert into lots."""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from typing import Any
import re

import requests
from django.core.management.base import BaseCommand
from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from land_monitor.db import SessionLocal
from land_monitor.models import Lot, Notice
from land_monitor.services.municipalities import sync_lot_municipality_refs
from land_monitor.services.regions import sync_lot_region_refs


API_URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
BASE_PARAMS = {
    "catCode": "2",
    "lotStatus": "PUBLISHED,APPLICATIONS_SUBMISSION",
    "sort": "firstVersionPublicationDate,desc",
    "withFacets": "false",
}
DEFAULT_REGION_CODE = "53"
DEFAULT_REGION_NAME = "Московская область"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


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


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _pick_first(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in raw and raw.get(key) is not None:
            return raw.get(key)
    return None


def _extract_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name") or value.get("code") or value.get("value") or None
    if isinstance(value, list):
        return ", ".join([str(item) for item in value])
    return str(value)


def _extract_number(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.replace(" ", "").replace(",", ".")
        try:
            return Decimal(cleaned)
        except Exception:
            return None
    if isinstance(value, dict):
        for key in ("value", "valueNum", "valueNumber"):
            if key in value:
                return _extract_number(value.get(key))
    return None


def _find_characteristic(raw: dict[str, Any], codes: list[str]) -> Any:
    characteristics = raw.get("characteristics")
    if not isinstance(characteristics, list):
        return None
    for item in characteristics:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if code in codes:
            return item.get("characteristicValue") if "characteristicValue" in item else item.get("value")
    return None


def _extract_cadastre_from_text(text: str | None) -> str | None:
    if not text:
        return None
    pattern = re.compile(r"\b\d{2}:\d{2}:\d{5,7}:\d+\b")
    match = pattern.search(text)
    return match.group(0) if match else None


def _extract_permitted_use(raw: dict[str, Any]) -> str | None:
    value = _find_characteristic(raw, ["PermittedUse"])
    if value is None:
        return None
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("value")
                if name:
                    names.append(str(name))
            elif isinstance(item, str):
                names.append(item)
        return ", ".join(names) if names else None
    if isinstance(value, dict):
        return _extract_text(value.get("name") or value.get("value") or value.get("code"))
    return _extract_text(value)


def _fetch_page(
    session: requests.Session,
    page: int,
    size: int,
    *,
    region_code: str,
    retry_count: int,
    backoff: list[float],
    delay: float,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None, float]:
    params = dict(BASE_PARAMS)
    params["dynSubjRF"] = region_code
    params["page"] = page
    params["size"] = size
    last_error: Exception | None = None
    last_error_code: str | None = None
    start = time.monotonic()
    for attempt in range(retry_count):
        try:
            response = session.get(API_URL, params=params, headers=HEADERS, timeout=10)
            status_code = response.status_code
            print(f"page={page} attempt={attempt+1} status_code={status_code}")
            if response.status_code == 503:
                last_error = RuntimeError("http_503")
                last_error_code = "http_503"
                if attempt < retry_count - 1:
                    sleep_for = backoff[min(attempt, len(backoff) - 1)]
                    print(f"page={page} attempt={attempt+1} retry_sleep={sleep_for} reason=http_503")
                    time.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                return [], None, "http_503", time.monotonic() - start
            response.raise_for_status()
            payload = response.json()
            content = payload.get("content") if isinstance(payload, dict) else []
            meta = None
            if isinstance(payload, dict):
                meta = {
                    "totalElements": payload.get("totalElements"),
                    "totalPages": payload.get("totalPages"),
                    "last": payload.get("last"),
                    "number": payload.get("number"),
                    "size": payload.get("size"),
                }
            return (content if isinstance(content, list) else []), meta, None, time.monotonic() - start
        except requests.exceptions.Timeout as exc:
            last_error = exc
            last_error_code = "timeout"
            print(f"page={page} attempt={attempt+1} error_type=timeout")
            if attempt < retry_count - 1:
                sleep_for = backoff[min(attempt, len(backoff) - 1)]
                print(f"page={page} attempt={attempt+1} retry_sleep={sleep_for} reason=timeout")
                time.sleep(sleep_for)
                continue
            break
        except Exception as exc:
            last_error = exc
            last_error_code = "error"
            print(f"page={page} attempt={attempt+1} error_type={type(exc).__name__}")
            if attempt < retry_count - 1:
                sleep_for = backoff[min(attempt, len(backoff) - 1)]
                print(f"page={page} attempt={attempt+1} retry_sleep={sleep_for} reason=error")
                time.sleep(backoff[min(attempt, len(backoff) - 1)])
                continue
            break
        finally:
            if delay > 0:
                time.sleep(delay)
    if last_error:
        return [], None, last_error_code, time.monotonic() - start
    return [], None, None, time.monotonic() - start


def _build_payload(
    raw: dict[str, Any],
    *,
    fallback_region_name: str,
    fallback_region_code: str,
) -> dict[str, Any]:
    source_lot_id = _pick_first(raw, ["id", "lotId", "lotNumber", "noticeNumber"])
    if not source_lot_id:
        raise ValueError("source_lot_id is required")
    source_lot_id = str(source_lot_id)

    source_url = _pick_first(raw, ["url", "lotUrl", "href"])
    if not source_url:
        source_url = f"https://torgi.gov.ru/new/public/lots/lot/{source_lot_id}"

    etp_code = _pick_first(raw, ["etpCode", "etp", "tradePlatformCode"])
    is_without_etp = etp_code is None or str(etp_code).strip() == ""

    notice_number = _pick_first(raw, ["noticeNumber", "noticeId"])
    if notice_number is not None:
        notice_number = str(notice_number)

    cadastre_number = _find_characteristic(raw, ["CadastralNumber", "cadastralNumberRealty"])
    cadastre_number = _extract_text(cadastre_number)
    if not cadastre_number:
        cadastre_number = _extract_cadastre_from_text(_extract_text(_pick_first(raw, ["lotDescription", "lotName"])))

    area_value = _find_characteristic(raw, ["SquareZU", "totalAreaRealty"])
    area_m2 = _extract_number(area_value)

    category_obj = raw.get("category")
    category_text = None
    if isinstance(category_obj, dict):
        category_text = _extract_text(category_obj.get("name") or category_obj.get("code"))
    else:
        category_text = _extract_text(category_obj)

    permitted_use = _extract_permitted_use(raw)

    price_min = _extract_number(_pick_first(raw, ["priceMin"]))
    deposit_amount = _extract_number(_pick_first(raw, ["deposit", "depositAmount"]))

    application_end_at = _parse_dt(_pick_first(raw, ["biddEndTime", "applicationEndDate"]))
    auction_start_at = _parse_dt(_pick_first(raw, ["auctionStartDate", "auctionDate"]))

    lot_status_external = _extract_text(_pick_first(raw, ["lotStatus"]))

    organizer_name = _extract_text(_pick_first(raw, ["organizerName"]))
    organizer_inn = _extract_text(_pick_first(raw, ["organizerInn"]))
    organizer_kpp = _extract_text(_pick_first(raw, ["organizerKpp"]))

    return {
        "source": "torgi",
        "source_lot_id": source_lot_id,
        "source_url": source_url,
        "notice_number": notice_number,
        "title": _extract_text(_pick_first(raw, ["lotName"])),
        "description": _extract_text(_pick_first(raw, ["lotDescription"])),
        "lot_status_external": lot_status_external,
        "region": _extract_text(_pick_first(raw, ["region"])) or fallback_region_name,
        "region_name": _extract_text(_pick_first(raw, ["region"])) or fallback_region_name,
        "source_torgi_region_code": fallback_region_code,
        "address": _extract_text(_pick_first(raw, ["estateAddress"])) or _extract_text(_pick_first(raw, ["address"])),
        "subject_rf_code": _extract_text(_pick_first(raw, ["subjectRFCode"])),
        "cadastre_number": cadastre_number,
        "area_m2": area_m2,
        "category": category_text,
        "permitted_use": permitted_use,
        "price_min": price_min,
        "deposit_amount": deposit_amount,
        "currency_code": _extract_text(_pick_first(raw, ["currencyCode"])),
        "etp_code": etp_code,
        "is_without_etp": is_without_etp,
        "organizer_name": organizer_name,
        "organizer_inn": organizer_inn,
        "organizer_kpp": organizer_kpp,
        "raw_data": raw,
    }


def _upsert_batch(db, items: list[dict[str, Any]]) -> int:
    if not items:
        return 0
    stmt = insert(Lot).values(items)
    update_cols = {}
    for key in items[0].keys():
        if key in {"source", "source_lot_id"}:
            continue
        update_cols[key] = getattr(stmt.excluded, key)

    if "updated_at" in Lot.__table__.columns:
        update_cols["updated_at"] = func.now()
    if "last_seen_at" in Lot.__table__.columns:
        update_cols["last_seen_at"] = func.now()

    stmt = stmt.on_conflict_do_update(
        index_elements=[Lot.source, Lot.source_lot_id],
        set_=update_cols,
    ).returning(Lot.id)
    result = db.execute(stmt)
    return len(result.fetchall())


def fetch_region_lots(
    *,
    region_code: str,
    region_name: str,
    stdout,
    limit: int | None,
    start_page: int,
    max_pages: int | None,
) -> dict[str, int | str | None]:
    size = 50
    backoff = [3.0, 7.0, 15.0]
    retry_count = 3
    delay = 0.7

    session = requests.Session()
    total_loaded = 0
    inserted = 0
    updated = 0
    stop_reason = None

    page = start_page
    pages_processed = 0
    last_page_processed = None
    db = SessionLocal()
    try:
        while True:
            if limit is not None and total_loaded >= limit:
                stop_reason = "limit_reached"
                break
            if max_pages is not None and pages_processed >= max_pages:
                stop_reason = "max_pages_reached"
                break
            stdout.write(f"region={region_name} region_code={region_code} page_start={page}")
            stdout.write(f"region={region_name} before_fetch page={page}")
            items, meta, fetch_error, elapsed = _fetch_page(
                session,
                page=page,
                size=size,
                region_code=region_code,
                retry_count=retry_count,
                backoff=backoff,
                delay=delay,
            )
            stdout.write(
                f"region={region_name} after_fetch page={page} fetched_items={len(items)} elapsed={elapsed:.2f}"
            )
            if not items:
                stop_reason = "http_503" if fetch_error == "http_503" else "empty_page"
                stdout.write(
                    f"region={region_name} page={page} fetched_items=0 "
                    f"totalElements={meta['totalElements'] if meta else None} "
                    f"totalPages={meta['totalPages'] if meta else None} last={meta['last'] if meta else None} "
                    f"total_loaded={total_loaded}"
                )
                break
            if limit is not None and total_loaded + len(items) > limit:
                items = items[: max(0, limit - total_loaded)]

            raw_notice_numbers = {
                str(_pick_first(item, ["noticeNumber", "noticeId"]))
                for item in items
                if _pick_first(item, ["noticeNumber", "noticeId"]) is not None
            }
            if raw_notice_numbers:
                stmt = insert(Notice).values(
                    [{"notice_number": num} for num in raw_notice_numbers]
                )
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=[Notice.notice_number]
                )
                db.execute(stmt)

            payloads = []
            for raw in items:
                try:
                    payload = _build_payload(
                        raw,
                        fallback_region_name=region_name,
                        fallback_region_code=region_code,
                    )
                    if "last_seen_at" in Lot.__table__.columns:
                        payload["last_seen_at"] = datetime.utcnow()
                    payloads.append(payload)
                except Exception:
                    continue

            if not payloads:
                stop_reason = "payloads_empty"
                stdout.write(
                    f"region={region_name} page={page} fetched_items={len(items)} "
                    f"totalElements={meta['totalElements'] if meta else None} "
                    f"totalPages={meta['totalPages'] if meta else None} last={meta['last'] if meta else None} "
                    f"total_loaded={total_loaded}"
                )
                break

            keys = [(p["source"], p["source_lot_id"]) for p in payloads]
            existing_keys = set(
                db.execute(
                    select(Lot.source, Lot.source_lot_id).where(
                        tuple_(Lot.source, Lot.source_lot_id).in_(keys)
                    )
                ).all()
            )

            stdout.write(f"region={region_name} before_upsert page={page} payloads={len(payloads)}")
            upserted = _upsert_batch(db, payloads)
            sync_lot_region_refs(db)
            sync_lot_municipality_refs(db)
            db.commit()
            total_loaded += len(payloads)
            inserted += sum(1 for key in keys if key not in existing_keys)
            updated += max(upserted - (len(keys) - len(existing_keys)), 0)
            stdout.write(f"region={region_name} after_commit page={page} total_loaded={total_loaded}")

            stdout.write(
                f"region={region_name} page={page} fetched_items={len(items)} "
                f"totalElements={meta['totalElements'] if meta else None} "
                f"totalPages={meta['totalPages'] if meta else None} last={meta['last'] if meta else None} "
                f"total_loaded={total_loaded}"
            )

            last_page_processed = page
            pages_processed += 1
            if meta and meta.get("last") is True:
                stop_reason = "last_page"
                break
            page += 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        session.close()

    return {
        "region_name": region_name,
        "region_code": region_code,
        "total_loaded": total_loaded,
        "inserted": inserted,
        "updated": updated,
        "pages_processed": pages_processed,
        "start_page": start_page,
        "end_page": last_page_processed if last_page_processed is not None else start_page - 1,
        "stop_reason": stop_reason,
    }


class Command(BaseCommand):
    help = "Fetch lots for Moscow region and upsert into lots table."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=150)
        parser.add_argument("--start-page", type=int, default=0)
        parser.add_argument("--max-pages", type=int, default=20)

    def handle(self, *args, **options):
        limit = int(options["limit"])
        start_page = int(options["start_page"])
        max_pages = int(options["max_pages"])
        result = fetch_region_lots(
            region_code=DEFAULT_REGION_CODE,
            region_name=DEFAULT_REGION_NAME,
            stdout=self.stdout,
            limit=limit,
            start_page=start_page,
            max_pages=max_pages,
        )

        db = SessionLocal()
        try:
            total_rows_in_db = db.execute(select(func.count()).select_from(Lot)).scalar() or 0
            examples = (
                db.query(Lot)
                .order_by(Lot.updated_at.desc())
                .limit(5)
                .all()
            )
        finally:
            db.close()

        self.stdout.write(f"total_loaded={result['total_loaded']}")
        self.stdout.write(f"inserted={result['inserted']}")
        self.stdout.write(f"updated={result['updated']}")
        self.stdout.write(f"total_rows_in_db={total_rows_in_db}")
        self.stdout.write(f"start_page={result['start_page']}")
        self.stdout.write(f"end_page={result['end_page']}")
        self.stdout.write(f"pages_processed={result['pages_processed']}")
        self.stdout.write(f"stop_reason={result['stop_reason']}")
        for lot in examples:
            self.stdout.write(
                f"example id={lot.id} source_lot_id={lot.source_lot_id} "
                f"etp_code={lot.etp_code} notice_number={lot.notice_number}"
            )
