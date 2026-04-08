"""Presentation helpers for Lot API responses."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from land_monitor.models import Lot, Notice


STATUS_LABELS: dict[str, str] = {
    "PUBLISHED": "Прием заявок",
    "APPLICATIONS_SUBMISSION": "Прием заявок",
    "CLOSED": "Завершен",
}


def _format_price(value: Decimal | int | float | None) -> str | None:
    if value is None:
        return None
    try:
        value_int = int(value)
    except (TypeError, ValueError):
        return None
    formatted = f"{value_int:,}".replace(",", " ")
    return f"{formatted} ₽"


def _format_area_sotka(value: Decimal | int | float | None) -> str | None:
    if value is None:
        return None
    try:
        area_m2 = Decimal(str(value))
    except (TypeError, ValueError):
        return None
    if area_m2 <= 0:
        return None
    sotka = area_m2 / Decimal("100")
    if sotka == sotka.to_integral_value():
        return f"{int(sotka)} соток"
    return f"{sotka.quantize(Decimal('0.1'))} соток"


def _map_status_label(status_raw: str | None) -> str | None:
    if not status_raw:
        return None
    return STATUS_LABELS.get(status_raw, status_raw)


def build_lot_response(lot: Lot, notice: Notice | None) -> dict[str, Any]:
    auction_site_url = getattr(notice, "auction_site_url", None) if notice else None
    application_portal_url = getattr(notice, "application_portal_url", None) if notice else None
    is_pre_auction = getattr(notice, "is_pre_auction", None) if notice else None
    is_39_18 = getattr(notice, "is_39_18", None) if notice else None

    if auction_site_url:
        participation = {
            "type": "auction",
            "label": "Торги",
            "url": auction_site_url,
            "source": "auction_site",
            "is_39_18": bool(is_39_18),
        }
    elif application_portal_url:
        participation = {
            "type": "application",
            "label": "Подача заявки",
            "url": application_portal_url,
            "source": "application_portal",
            "is_39_18": bool(is_39_18),
        }
    elif is_pre_auction:
        participation = {
            "type": "application",
            "label": "Подача заявки",
            "url": None,
            "source": "pre_auction_no_url",
            "is_39_18": bool(is_39_18),
        }
    else:
        participation = {
            "type": "none",
            "label": "Нет данных",
            "url": None,
            "source": "unknown",
            "is_39_18": bool(is_39_18),
        }

    status = {
        "code": lot.lot_status_external,
        "label": _map_status_label(lot.lot_status_external),
    }

    location = {
        "region_name": lot.region_name or lot.region,
        "municipality_name": lot.municipality_name,
        "label": lot.municipality_name or lot.region_name or lot.region,
    }

    price = {
        "value": lot.price_min,
        "display": _format_price(lot.price_min),
    }

    area = {
        "m2": lot.area_m2,
        "sotka_display": _format_area_sotka(lot.area_m2),
    }

    return {
        "id": lot.id,
        "source_lot_id": lot.source_lot_id,
        "title": lot.title,
        "description": lot.description,
        "lot_status_external": lot.lot_status_external,
        "status_label": _map_status_label(lot.lot_status_external),
        "status": status,
        "region_name": lot.region_name or lot.region,
        "municipality_name": lot.municipality_name,
        "location": location,
        "price_min": lot.price_min,
        "price_display": _format_price(lot.price_min),
        "price": price,
        "area_m2": lot.area_m2,
        "area_display": _format_area_sotka(lot.area_m2),
        "area": area,
        "source_url": lot.source_url,
        "notice_number": lot.notice_number,
        "notice": {"notice_number": lot.notice_number},
        "participation": participation,
        "is_39_18": bool(is_39_18),
        "links": {
            "lot_url": lot.source_url,
            "auction_site_url": auction_site_url,
            "application_portal_url": application_portal_url,
        },
    }
