"""Smoke test for query services."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from land_monitor.db import SessionLocal
from land_monitor.services.auctions import (
    get_auction_card_public,
    list_auctions_public,
    list_parser_runs_public,
    list_recent_auctions_public,
    list_top_cheapest_by_sotka_public,
)


def main() -> int:
    db = SessionLocal()

    try:
        print("=== Auctions (limit 5) ===")
        for item in list_auctions_public(db, limit=5):
            print(item)

        print("\n=== Recent Auctions ===")
        for item in list_recent_auctions_public(db, limit=5):
            print(item)

        print("\n=== Parser Runs ===")
        for item in list_parser_runs_public(db, limit=10):
            print(item)

        print("\n=== Cheapest by price_per_sotka ===")
        for item in list_top_cheapest_by_sotka_public(db, limit=10):
            print(item)

        print("\n=== Auction #1 ===")
        auction_card = get_auction_card_public(db, 1)
        if auction_card is None:
            print("Auction with id=1 not found.")
        else:
            print(auction_card)

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
