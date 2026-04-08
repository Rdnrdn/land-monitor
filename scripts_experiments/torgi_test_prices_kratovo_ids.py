"""Print published land lot ids and priceMin for Kratovo."""

from __future__ import annotations

import json
from typing import Any

import requests


URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
TIMEOUT = 15
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://torgi.gov.ru/new/public/lots/reg",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
PARAMS = {
    "fiasGUID": "85de79fc-9f86-4caf-b5f5-6c30775cd4a4",
    "catCode": "2",
    "lotStatus": "PUBLISHED",
    "byFirstVersion": "true",
    "withFacets": "true",
    "size": 100,
    "sort": "priceMin,asc",
}


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get("content")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def main() -> int:
    session = requests.Session()
    response = session.get(URL, params=PARAMS, headers=HEADERS, timeout=TIMEOUT)
    payload = response.json()
    items = extract_items(payload)
    total_elements = payload.get("totalElements") if isinstance(payload, dict) else None

    print("==== KRATOVO LAND PUBLISHED ====")
    print(f"totalElements={total_elements}")
    print()
    print("id priceMin")
    for item in items:
        lot_id = item.get("id")
        price_min = item.get("priceMin", None)
        price_out = "null" if price_min is None else str(price_min)
        print(f"{lot_id} {price_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
