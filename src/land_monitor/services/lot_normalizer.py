"""Normalize raw torgi.gov lot items into internal lots payload."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


def _pick_first(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return value
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(candidate)
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


def _derive_status_flags(status: str | None) -> tuple[bool | None, bool | None]:
    if status is None:
        return None, None
    normalized = status.upper()
    active_statuses = {"PUBLISHED", "APPLICATIONS_SUBMISSION"}
    finished_statuses = {"FINISHED", "CANCELLED", "FAILED", "COMPLETED", "CLOSED"}
    if normalized in active_statuses:
        return True, False
    if normalized in finished_statuses:
        return False, True
    return None, None


def _price_bucket(price: Decimal | None) -> str | None:
    if price is None:
        return None
    value = float(price)
    if value <= 1_000_000:
        return "under_1m"
    if value <= 2_000_000:
        return "from_1m_to_2m"
    if value <= 5_000_000:
        return "from_2m_to_5m"
    if value <= 10_000_000:
        return "from_5m_to_10m"
    if value <= 50_000_000:
        return "from_10m_to_50m"
    return "over_50m"


def normalize_lot(
    raw: dict[str, Any],
    source: str = "torgi",
    source_torgi_region_code: str | None = None,
) -> dict[str, Any]:
    source_lot_id = _pick_first(raw, ["id", "lotId", "lotNumber", "noticeNumber"])
    if not source_lot_id:
        raise ValueError("source_lot_id is required")

    source_lot_id = str(source_lot_id)
    source_url = _pick_first(raw, ["url", "lotUrl", "href"])
    if not source_url:
        source_url = f"https://torgi.gov.ru/new/public/lots/lot/{source_lot_id}"

    title = _pick_first(raw, ["lotName", "name", "title"])
    description = _pick_first(raw, ["description", "lotDescription"])
    region_name = _pick_first(raw, ["region", "regionName", "subjectRFName"])

    price_min = _to_decimal(_pick_first(raw, ["priceMin", "startPrice", "startPriceAmount"]))
    price_fin = _to_decimal(_pick_first(raw, ["priceFin", "finalPrice"]))
    deposit_amount = _to_decimal(_pick_first(raw, ["depositAmount", "deposit"]))

    application_deadline = _parse_datetime(_pick_first(raw, ["applicationDeadline", "applicationEndDate"]))
    application_start_date = _parse_datetime(_pick_first(raw, ["applicationStartDate", "applicationBeginDate"]))
    auction_date = _parse_datetime(_pick_first(raw, ["auctionDate", "biddingDate"]))

    status_external = _pick_first(raw, ["lotStatus", "status", "statusCode"])
    is_active, is_finished = _derive_status_flags(str(status_external) if status_external else None)

    days_to_deadline = None
    if application_deadline:
        delta = application_deadline.date() - datetime.utcnow().date()
        days_to_deadline = delta.days

    is_price_null = price_min is None
    etp_code = _pick_first(raw, ["etpCode", "etp", "tradePlatformCode"])
    is_etp_empty = etp_code is None or str(etp_code).strip() == ""

    return {
        "source": source,
        "source_lot_id": source_lot_id,
        "source_url": source_url,
        "title": title,
        "description": description,
        "region": region_name,
        "region_name": region_name,
        "source_torgi_region_code": source_torgi_region_code,
        "subject_rf_code": _pick_first(raw, ["subjectRFCode"]),
        "district": _pick_first(raw, ["district", "districtName", "municipalityName"]),
        "address": _pick_first(raw, ["address", "addressText"]),
        "fias_guid": _pick_first(raw, ["fiasGuid", "fiasGUID"]),
        "cadastre_number": _pick_first(raw, ["cadastreNumber", "cadastre_number"]),
        "area_m2": _to_decimal(_pick_first(raw, ["lotArea", "area", "areaM2"])),
        "category": _pick_first(raw, ["category", "categoryCode", "categoryName"]),
        "permitted_use": _pick_first(raw, ["permittedUse", "permittedUseName"]),
        "price_min": price_min,
        "price_fin": price_fin,
        "deposit_amount": deposit_amount,
        "currency_code": _pick_first(raw, ["currencyCode", "currency"]),
        "etp_code": etp_code,
        "etp_name": _pick_first(raw, ["etpName", "tradePlatformName"]),
        "organizer_name": _pick_first(raw, ["organizerName", "organizerFullName"]),
        "organizer_inn": _pick_first(raw, ["organizerInn", "inn"]),
        "organizer_kpp": _pick_first(raw, ["organizerKpp", "kpp"]),
        "lot_status_external": str(status_external) if status_external is not None else None,
        "is_active": is_active,
        "is_finished": is_finished,
        "application_start_date": application_start_date,
        "application_deadline": application_deadline,
        "auction_date": auction_date,
        "source_created_at": _parse_datetime(_pick_first(raw, ["createdAt", "createDate"])),
        "source_updated_at": _parse_datetime(_pick_first(raw, ["updatedAt", "updateDate"])),
        "price_bucket": _price_bucket(price_min),
        "days_to_deadline": days_to_deadline,
        "is_price_null": is_price_null,
        "is_etp_empty": is_etp_empty,
        "score": None,
        "segment": None,
        "raw_data": raw,
    }
