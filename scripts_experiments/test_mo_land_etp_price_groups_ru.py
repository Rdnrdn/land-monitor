#!/usr/bin/env python3
import json
import time
from collections import Counter
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT_SECONDS = 30
RETRIES = 3
RETRY_SLEEP_SECONDS = 2.5
REGION = "54"
LOT_STATUS = "PUBLISHED,APPLICATIONS_SUBMISSION"

ETP_NAMES = {
    "ETP_RTS": "РТС-тендер",
    "ETP_RAD": "РАД",
    "ETP_MMVB": "ММВБ",
    "ETP_SBAST": "Сбер А",
    "EMPTY": "Площадка не указана",
}


def fetch_json(params: dict):
    url = f"{BASE_URL}?{urlencode(params)}"
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_error = e
            if attempt < RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS)
    raise last_error


def price_bucket(price):
    if price is None:
        return "price_null"
    value = float(price)
    if value < 1_000_000:
        return "under_1m"
    if value < 2_000_000:
        return "from_1m_to_2m"
    if value < 5_000_000:
        return "from_2m_to_5m"
    if value < 10_000_000:
        return "from_5m_to_10m"
    if value < 50_000_000:
        return "from_10m_to_50m"
    return "over_50m"


def normalize_etp(item):
    etp = item.get("etpCode")
    if etp is None or not str(etp).strip():
        return "EMPTY"
    return str(etp)


def main():
    stats_params = {
        "dynSubjRF": REGION,
        "catCode": "2",
        "lotStatus": LOT_STATUS,
        "withFacets": "true",
        "size": 1,
    }
    first_page_params = {
        "dynSubjRF": REGION,
        "catCode": "2",
        "lotStatus": LOT_STATUS,
        "withFacets": "false",
        "size": 20,
        "offset": 0,
        "sort": "firstVersionPublicationDate,desc",
    }

    stats = fetch_json(stats_params)
    data = fetch_json(first_page_params)
    items = data.get("content") or []

    etp_counter = Counter(normalize_etp(item) for item in items)
    price_counter = Counter(price_bucket(item.get("priceMin")) for item in items)

    total_unique = stats.get("totalElements")
    total_published = None
    total_applications_submission = None

    facets = stats.get("facets") or []
    for facet in facets:
        if facet.get("name") in ("lotStatus", "lotStatus.keyword"):
            for bucket in facet.get("values") or []:
                if bucket.get("value") == "PUBLISHED":
                    total_published = bucket.get("count")
                elif bucket.get("value") == "APPLICATIONS_SUBMISSION":
                    total_applications_submission = bucket.get("count")

    print("==== SUMMARY ====")
    print(f"total_unique={total_unique}")
    print(f"total_published={total_published}")
    print(f"total_applications_submission={total_applications_submission}")
    print()
    print("==== GROUP BY ETP ====")
    for key in ["EMPTY", "ETP_MMVB", "ETP_RAD", "ETP_RTS", "ETP_SBAST"]:
        print(f"{key}={etp_counter.get(key, 0)}")
    print()
    print("==== GROUP BY PRICE ====")
    for key in ["under_1m", "from_1m_to_2m", "from_2m_to_5m", "from_5m_to_10m", "from_10m_to_50m", "over_50m", "price_null"]:
        print(f"{key}={price_counter.get(key, 0)}")
    print()
    print(f"unique_lots={len(items)}")


if __name__ == "__main__":
    main()
