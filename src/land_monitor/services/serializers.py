"""Serialization helpers for service-layer responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize_plot(plot: Any) -> dict[str, Any] | None:
    if plot is None:
        return None

    return {
        "id": plot.id,
        "source_id": plot.source_id,
        "region": plot.region,
        "cadastre_number": plot.cadastre_number,
        "title": plot.title,
        "address": plot.address,
        "area": _serialize_value(plot.area),
        "area_sotka": _serialize_value(plot.area_sotka),
        "latitude": _serialize_value(plot.latitude),
        "longitude": _serialize_value(plot.longitude),
        "status": plot.status,
        "created_at": _serialize_value(plot.created_at),
        "updated_at": _serialize_value(plot.updated_at),
    }


def serialize_auction(auction: Any) -> dict[str, Any] | None:
    if auction is None:
        return None

    return {
        "id": auction.id,
        "source_id": auction.source_id,
        "plot_id": auction.plot_id,
        "source_run_id": auction.source_run_id,
        "external_id": auction.external_id,
        "source_url": auction.source_url,
        "region": auction.region,
        "start_price": _serialize_value(auction.start_price),
        "current_price": _serialize_value(auction.current_price),
        "final_price": _serialize_value(auction.final_price),
        "price_per_sotka": _serialize_value(auction.price_per_sotka),
        "currency": auction.currency,
        "status": auction.status,
        "raw_json": auction.raw_json,
        "created_at": _serialize_value(auction.created_at),
        "updated_at": _serialize_value(auction.updated_at),
    }


def serialize_price_history(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None

    return {
        "id": item.id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "auction_id": item.auction_id,
        "listing_id": item.listing_id,
        "price": _serialize_value(item.price),
        "currency": item.currency,
        "recorded_at": _serialize_value(item.recorded_at),
        "created_at": _serialize_value(item.created_at),
    }


def serialize_source_run(run: Any) -> dict[str, Any] | None:
    if run is None:
        return None

    return {
        "id": run.id,
        "source_id": run.source_id,
        "status": run.status,
        "started_at": _serialize_value(run.started_at),
        "finished_at": _serialize_value(run.finished_at),
        "message": run.message,
        "created_at": _serialize_value(run.created_at),
        "updated_at": _serialize_value(run.updated_at),
    }
