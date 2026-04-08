"""Public web-safe response builders."""

from __future__ import annotations

from typing import Any


def auction_public_view(auction_dict: dict[str, Any] | None) -> dict[str, Any] | None:
    if auction_dict is None:
        return None

    return {
        "id": auction_dict.get("id"),
        "external_id": auction_dict.get("external_id"),
        "region": auction_dict.get("region"),
        "start_price": auction_dict.get("start_price"),
        "price_per_sotka": auction_dict.get("price_per_sotka"),
        "status": auction_dict.get("status"),
        "source_url": auction_dict.get("source_url"),
        "created_at": auction_dict.get("created_at"),
    }


def auction_card_public_view(card_dict: dict[str, Any] | None) -> dict[str, Any] | None:
    if card_dict is None:
        return None

    plot = card_dict.get("plot")
    price_history = card_dict.get("price_history") or []

    return {
        "auction": auction_public_view(card_dict.get("auction")),
        "plot": (
            {
                "cadastre_number": plot.get("cadastre_number"),
                "title": plot.get("title"),
                "address": plot.get("address"),
                "area": plot.get("area"),
                "area_sotka": plot.get("area_sotka"),
                "region": plot.get("region"),
            }
            if plot
            else None
        ),
        "price_history": [
            {
                "price": item.get("price"),
                "recorded_at": item.get("recorded_at"),
            }
            for item in price_history
        ],
    }


def parser_run_public_view(run_dict: dict[str, Any] | None) -> dict[str, Any] | None:
    if run_dict is None:
        return None

    return {
        "id": run_dict.get("id"),
        "status": run_dict.get("status"),
        "started_at": run_dict.get("started_at"),
        "finished_at": run_dict.get("finished_at"),
        "message": run_dict.get("message"),
        "created_at": run_dict.get("created_at"),
    }
