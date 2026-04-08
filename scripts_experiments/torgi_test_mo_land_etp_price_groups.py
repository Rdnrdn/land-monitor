"""Diagnostics: Moscow region land lots by etpCode and price ranges."""

from __future__ import annotations

import math
import requests


URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
TIMEOUT = 20
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
    "dynSubjRF": "53",
    "catCode": "2",
    "lotStatus": "PUBLISHED,APPLICATIONS_SUBMISSION",
    "byFirstVersion": "true",
    "withFacets": "true",
    "size": 200,
    "sort": "firstVersionPublicationDate,desc",
}


def extract_items(payload: dict) -> list[dict]:
    value = payload.get("content")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def price_bucket(price: float) -> str:
    if price <= 1_000_000:
        return "under_1m"
    if price <= 2_000_000:
        return "from_1m_to_2m"
    if price <= 5_000_000:
        return "from_2m_to_5m"
    if price <= 10_000_000:
        return "from_5m_to_10m"
    if price <= 50_000_000:
        return "from_10m_to_50m"
    return "over_50m"


def main() -> int:
    session = requests.Session()

    params = dict(BASE_PARAMS)
    params["page"] = 0
    response = session.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    payload = response.json() if isinstance(response.json(), dict) else {}

    total_elements = payload.get("totalElements")
    size = payload.get("size") or BASE_PARAMS["size"]
    try:
        size = int(size)
    except Exception:
        size = BASE_PARAMS["size"]

    if isinstance(total_elements, int) and total_elements > 0:
        pages_total = int(math.ceil(total_elements / size))
    else:
        pages_total = 1

    seen: set[str] = set()
    count_by_etp: dict[str, int] = {}
    count_by_price: dict[str, int] = {
        "under_1m": 0,
        "from_1m_to_2m": 0,
        "from_2m_to_5m": 0,
        "from_5m_to_10m": 0,
        "from_10m_to_50m": 0,
        "over_50m": 0,
        "price_null": 0,
    }
    total_published = 0
    total_applications = 0

    for page in range(pages_total):
        params = dict(BASE_PARAMS)
        params["page"] = page
        resp = session.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
        page_payload = resp.json()
        if not isinstance(page_payload, dict):
            continue
        items = extract_items(page_payload)

        for item in items:
            lot_id = item.get("id")
            if lot_id is None:
                continue
            lot_id = str(lot_id)
            if lot_id in seen:
                continue
            seen.add(lot_id)

            status = item.get("lotStatus") or item.get("status")
            if status == "PUBLISHED":
                total_published += 1
            elif status == "APPLICATIONS_SUBMISSION":
                total_applications += 1

            etp = item.get("etpCode")
            if etp is None or str(etp).strip() == "":
                etp = "EMPTY"
            count_by_etp[etp] = count_by_etp.get(etp, 0) + 1

            price = item.get("priceMin")
            if price is None or str(price).strip() == "":
                count_by_price["price_null"] += 1
            else:
                try:
                    bucket = price_bucket(float(price))
                    count_by_price[bucket] += 1
                except (TypeError, ValueError):
                    count_by_price["price_null"] += 1

    print("==== SUMMARY ====")
    print(f"total_unique={len(seen)}")
    print(f"total_published={total_published}")
    print(f"total_applications_submission={total_applications}")
    print()
    print("==== GROUP BY ETP ====")
    for key in sorted(count_by_etp.keys()):
        print(f"{key}={count_by_etp[key]}")
    print()
    print("==== GROUP BY PRICE ====")
    print(f"under_1m={count_by_price['under_1m']}")
    print(f"from_1m_to_2m={count_by_price['from_1m_to_2m']}")
    print(f"from_2m_to_5m={count_by_price['from_2m_to_5m']}")
    print(f"from_5m_to_10m={count_by_price['from_5m_to_10m']}")
    print(f"from_10m_to_50m={count_by_price['from_10m_to_50m']}")
    print(f"over_50m={count_by_price['over_50m']}")
    print(f"price_null={count_by_price['price_null']}")
    print()
    print(f"unique_lots={len(seen)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
