"""Full pagination price grouping for Borovsky district land lots."""

from __future__ import annotations

import math
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
BASE_PARAMS = {
    "fiasGUID": "d3d0c365-e160-43c3-94e3-b593f92f4c22",
    "catCode": "2",
    "lotStatus": "APPLICATIONS_SUBMISSION",
    "byFirstVersion": "true",
    "withFacets": "true",
    "size": 100,
    "sort": "priceMin,asc",
}


def extract_items(payload: dict) -> list[dict]:
    value = payload.get("content")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def classify_price(price: float, counters: dict[str, int]) -> None:
    if price <= 1_000_000:
        counters["under_1m"] += 1
    elif price <= 2_000_000:
        counters["from_1000001_to_2m"] += 1
    elif price < 3_000_000:
        counters["between_2m_3m"] += 1
    else:
        counters["from_3m"] += 1


def main() -> int:
    session = requests.Session()

    # First page to get totalElements and page size
    params = dict(BASE_PARAMS)
    params["page"] = 0
    response = session.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    payload = response.json() if isinstance(response.json(), dict) else {}

    total_elements = payload.get("totalElements")
    size = payload.get("size") or BASE_PARAMS["size"]
    if not isinstance(size, int):
        size = BASE_PARAMS["size"]

    pages_total = 0
    if isinstance(total_elements, int) and total_elements > 0:
        pages_total = int(math.ceil(total_elements / size))
    elif isinstance(total_elements, int) and total_elements == 0:
        pages_total = 1
    else:
        pages_total = 1

    counters = {
        "under_1m": 0,
        "from_1000001_to_2m": 0,
        "between_2m_3m": 0,
        "from_3m": 0,
        "price_null_count": 0,
    }

    all_items: list[dict] = []
    pages_loaded = 0

    for page in range(pages_total):
        params = dict(BASE_PARAMS)
        params["page"] = page
        resp = session.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
        page_payload = resp.json()
        if not isinstance(page_payload, dict):
            continue
        items = extract_items(page_payload)
        all_items.extend(items)
        pages_loaded += 1

    for item in all_items:
        price = item.get("priceMin") if isinstance(item, dict) else None
        if price is None:
            counters["price_null_count"] += 1
            continue
        try:
            classify_price(float(price), counters)
        except (TypeError, ValueError):
            counters["price_null_count"] += 1

    items_loaded = len(all_items)

    print("==== BOROVSKY APPLICATIONS LAND FULL ====")
    print(f"totalElements={total_elements}")
    print(f"pages_loaded={pages_loaded}")
    print(f"items_loaded={items_loaded}")
    print()
    print(f"under_1m={counters['under_1m']}")
    print(f"from_1000001_to_2m={counters['from_1000001_to_2m']}")
    print(f"between_2m_3m={counters['between_2m_3m']}")
    print(f"from_3m={counters['from_3m']}")
    print(f"price_null_count={counters['price_null_count']}")
    print()
    print("id priceMin")
    for item in all_items:
        if not isinstance(item, dict):
            continue
        lot_id = item.get("id")
        price = item.get("priceMin")
        price_out = "null" if price is None else str(price)
        print(f"{lot_id} {price_out}")
    print()

    counted_total = (
        counters["under_1m"]
        + counters["from_1000001_to_2m"]
        + counters["between_2m_3m"]
        + counters["from_3m"]
        + counters["price_null_count"]
    )
    print(f"counted_total={counted_total}")
    print(f"counted_matches_items_loaded={'true' if counted_total == items_loaded else 'false'}")
    if isinstance(total_elements, int) and total_elements != items_loaded:
        print("warning_totalElements_mismatch=true")
        print(f"totalElements_reported={total_elements}")
        print(f"items_loaded_actual={items_loaded}")
    else:
        print("warning_totalElements_mismatch=false")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
