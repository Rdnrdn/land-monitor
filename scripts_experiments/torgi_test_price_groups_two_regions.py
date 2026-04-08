"""Group land lots by price for two regions (applications submission)."""

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
BASE_PARAMS = {
    "catCode": "2",
    "lotStatus": "APPLICATIONS_SUBMISSION",
    "byFirstVersion": "true",
    "withFacets": "true",
    "size": 100,
    "sort": "priceMin,asc",
}
TESTS = [
    ("narofominsk_applications_land", "0d5fdd1b-a7fa-452e-bde7-6f752016d67b"),
    ("borovsky_applications_land", "d3d0c365-e160-43c3-94e3-b593f92f4c22"),
]


def classify_price(price: float, counters: dict[str, int]) -> None:
    if price <= 1_000_000:
        counters["under_1m"] += 1
    elif price <= 2_000_000:
        counters["under_2m"] += 1
    elif price <= 3_000_000:
        counters["between_2m_3m"] += 1
    else:
        counters["over_3m"] += 1


def main() -> int:
    session = requests.Session()
    summary: dict[str, dict[str, int | None]] = {}

    for test_name, fias_guid in TESTS:
        params = dict(BASE_PARAMS)
        params["fiasGUID"] = fias_guid

        response = session.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
        payload = response.json()
        items = payload.get("content") if isinstance(payload, dict) else []
        if not isinstance(items, list):
            items = []

        total_elements = payload.get("totalElements") if isinstance(payload, dict) else None

        counters = {
            "under_1m": 0,
            "under_2m": 0,
            "between_2m_3m": 0,
            "over_3m": 0,
            "price_null_count": 0,
        }

        for item in items:
            if not isinstance(item, dict):
                continue
            price = item.get("priceMin")
            if price is None:
                counters["price_null_count"] += 1
                continue
            try:
                classify_price(float(price), counters)
            except (TypeError, ValueError):
                counters["price_null_count"] += 1

        print("==== REGION ====")
        print(f"test_name={test_name}")
        print(f"totalElements={total_elements}")
        print(f"under_1m={counters['under_1m']}")
        print(f"under_2m={counters['under_2m']}")
        print(f"between_2m_3m={counters['between_2m_3m']}")
        print(f"over_3m={counters['over_3m']}")
        print(f"price_null_count={counters['price_null_count']}")
        print()
        print("id priceMin")
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            lot_id = item.get("id")
            price = item.get("priceMin")
            price_out = "null" if price is None else str(price)
            print(f"{lot_id} {price_out}")
        print()

        summary[test_name] = {
            "total": total_elements if isinstance(total_elements, int) else None,
            "under_1m": counters["under_1m"],
            "under_2m": counters["under_2m"],
            "between_2m_3m": counters["between_2m_3m"],
            "over_3m": counters["over_3m"],
            "price_null_count": counters["price_null_count"],
        }

    print("==== SUMMARY ====")
    for test_name, data in summary.items():
        print(f"{test_name}:")
        print(f"  total={data['total']}")
        print(f"  under_1m={data['under_1m']}")
        print(f"  under_2m={data['under_2m']}")
        print(f"  between_2m_3m={data['between_2m_3m']}")
        print(f"  over_3m={data['over_3m']}")
        print(f"  price_null_count={data['price_null_count']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
