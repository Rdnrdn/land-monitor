"""Count published land lots in Moscow region (dynSubjRF=53)."""

from __future__ import annotations

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
    "dynSubjRF": "53",
    "catCode": "2",
    "lotStatus": "PUBLISHED",
    "byFirstVersion": "true",
    "withFacets": "true",
    "size": 10,
    "sort": "firstVersionPublicationDate,desc",
}


def main() -> int:
    session = requests.Session()
    response = session.get(URL, params=PARAMS, headers=HEADERS, timeout=TIMEOUT)
    payload = response.json()
    total_elements = payload.get("totalElements") if isinstance(payload, dict) else None
    number_of_elements = payload.get("numberOfElements") if isinstance(payload, dict) else None
    items = payload.get("content") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []

    print("==== MOSCOW REGION LAND PUBLISHED ====")
    print(f"totalElements={total_elements}")
    print(f"numberOfElements={number_of_elements}")
    print()
    print("id priceMin")
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        lot_id = item.get("id")
        price_min = item.get("priceMin")
        price_out = "null" if price_min is None else str(price_min)
        print(f"{lot_id} {price_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
