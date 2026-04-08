"""Telegram-friendly command outputs for land-monitor."""

from __future__ import annotations

from land_monitor.db import SessionLocal
from land_monitor.services.auctions import (
    count_auctions,
    get_auction_card_public,
    list_parser_runs_public,
    list_recent_auctions_public,
    list_top_cheapest_by_sotka_public,
)


def cmd_status() -> str:
    db = SessionLocal()
    try:
        recent = list_recent_auctions_public(db, limit=1)
        runs = list_parser_runs_public(db, limit=1)
        auctions_count = count_auctions(db)

        lines = ["land-monitor status"]
        lines.append(f"Recent auctions available: {auctions_count}")
        if recent:
            lines.append(f"Latest auction: #{recent[0]['id']} {recent[0]['external_id']}")
        else:
            lines.append("Latest auction: no data")

        if runs:
            lines.append(f"Latest parser run: #{runs[0]['id']} {runs[0]['status']}")
        else:
            lines.append("Latest parser run: no data")

        return "\n".join(lines)
    finally:
        db.close()


def cmd_recent(limit: int = 5) -> str:
    db = SessionLocal()
    try:
        items = list_recent_auctions_public(db, limit=limit)
        if not items:
            return "No recent auctions found."

        lines = [f"Recent auctions ({len(items)}):"]
        for item in items:
            lines.append(
                f"#{item['id']} {item['external_id']} | {item['region']} | "
                f"{item['start_price']} | {item['price_per_sotka']} per sotka"
            )
        return "\n".join(lines)
    finally:
        db.close()


def cmd_cheapest(limit: int = 5, region: str | None = None) -> str:
    db = SessionLocal()
    try:
        items = list_top_cheapest_by_sotka_public(db, limit=limit, region=region)
        if not items:
            return "No cheap auctions found."

        title = f"Cheapest auctions ({len(items)})"
        if region:
            title += f" in {region}"

        lines = [title + ":"]
        for item in items:
            lines.append(
                f"#{item['id']} {item['external_id']} | {item['region']} | "
                f"{item['price_per_sotka']} per sotka | {item['start_price']}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def cmd_auction(auction_id: int) -> str:
    db = SessionLocal()
    try:
        card = get_auction_card_public(db, auction_id)
        if card is None:
            return f"Auction #{auction_id} not found."

        auction = card["auction"]
        plot = card["plot"]
        price_history = card["price_history"]

        lines = [
            f"Auction #{auction['id']}",
            f"External ID: {auction['external_id']}",
            f"Region: {auction['region']}",
            f"Start price: {auction['start_price']}",
            f"Price per sotka: {auction['price_per_sotka']}",
            f"Status: {auction['status']}",
            f"URL: {auction['source_url']}",
        ]

        if plot:
            lines.extend(
                [
                    "Plot:",
                    f"  Cadastre: {plot['cadastre_number']}",
                    f"  Title: {plot['title']}",
                    f"  Area: {plot['area']}",
                    f"  Area sotka: {plot['area_sotka']}",
                ]
            )

        if price_history:
            lines.append("Price history:")
            for item in price_history[:5]:
                lines.append(f"  {item['recorded_at']} -> {item['price']}")
        else:
            lines.append("Price history: no data")

        return "\n".join(lines)
    finally:
        db.close()


def cmd_runs(limit: int = 5) -> str:
    db = SessionLocal()
    try:
        items = list_parser_runs_public(db, limit=limit)
        if not items:
            return "No parser runs found."

        lines = [f"Parser runs ({len(items)}):"]
        for item in items:
            lines.append(
                f"#{item['id']} | {item['status']} | {item['created_at']} | {item['message']}"
            )
        return "\n".join(lines)
    finally:
        db.close()
