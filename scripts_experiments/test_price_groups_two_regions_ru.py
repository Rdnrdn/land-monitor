#!/usr/bin/env python3
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT_SECONDS = 30
RETRIES = 3
RETRY_SLEEP_SECONDS = 2.5
LOT_STATUS = "PUBLISHED,APPLICATIONS_SUBMISSION"

REGIONS = [
    ("narofominsk_applications_land", "54"),
    ("borovsky_applications_land", "54"),
]


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


def count_groups(items):
    under_1m = 0
    under_2m = 0
    between_2m_3m = 0
    over_3m = 0
    price_null_count = 0
    for item in items:
        price = item.get("priceMin")
        if price is None:
            price_null_count += 1
            continue
        price = float(price)
        if price < 1_000_000:
            under_1m += 1
        elif price < 2_000_000:
            under_2m += 1
        elif price < 3_000_000:
            between_2m_3m += 1
        else:
            over_3m += 1
    return under_1m, under_2m, between_2m_3m, over_3m, price_null_count


def main():
    summary = []
    for test_name, region in REGIONS:
        params = {
            "dynSubjRF": region,
            "catCode": "2",
            "lotStatus": LOT_STATUS,
            "withFacets": "false",
            "size": 10,
            "offset": 0,
            "sort": "firstVersionPublicationDate,desc",
        }
        data = fetch_json(params)
        items = data.get("content") or []
        under_1m, under_2m, between_2m_3m, over_3m, price_null_count = count_groups(items)

        print("==== REGION ====")
        print(f"test_name={test_name}")
        print(f"totalElements={data.get('totalElements')}")
        print(f"under_1m={under_1m}")
        print(f"under_2m={under_2m}")
        print(f"between_2m_3m={between_2m_3m}")
        print(f"over_3m={over_3m}")
        print(f"price_null_count={price_null_count}")
        print()
        print("id priceMin")
        for item in items:
            print(f"{item.get('id')} {item.get('priceMin')}")
        print()

        summary.append((test_name, data.get("totalElements"), under_1m, under_2m, between_2m_3m, over_3m, price_null_count))

    print("==== SUMMARY ====")
    for row in summary:
        print(f"{row[0]}:")
        print(f"  total={row[1]}")
        print(f"  under_1m={row[2]}")
        print(f"  under_2m={row[3]}")
        print(f"  between_2m_3m={row[4]}")
        print(f"  over_3m={row[5]}")
        print(f"  price_null_count={row[6]}")
        print()


if __name__ == "__main__":
    main()
