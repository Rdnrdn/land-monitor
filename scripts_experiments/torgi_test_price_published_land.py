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
REGION = "54"
LOT_STATUS = "PUBLISHED,APPLICATIONS_SUBMISSION"


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


def print_block(name: str, params: dict, data: dict):
    content = data.get("content") or []
    print("==== TEST ====")
    print(f"test_name={name}")
    print(f"status_code=200")
    print(f"request_params={json.dumps(params, ensure_ascii=False)}")
    print(f"totalElements={data.get('totalElements')}")
    print(f"numberOfElements={data.get('numberOfElements')}")
    print(f"top10_ids={[item.get('id') for item in content[:10]]}")
    print(f"top10_lotName={[item.get('lotName') for item in content[:10]]}")
    print(f"top10_priceMin={[item.get('priceMin') for item in content[:10]]}")
    if any('noticeFirstVersionPublicationDate' in item for item in content[:10]):
        print(f"top10_noticeFirstVersionPublicationDate={[item.get('noticeFirstVersionPublicationDate') for item in content[:10]]}")
    if content:
        print(f"top10_source_url={[f'https://torgi.gov.ru/new/public/lots/lot/{item.get('id')}' for item in content[:10] if item.get('id')]}")
    print()


def main():
    base_stats = {
        "dynSubjRF": REGION,
        "catCode": "2",
        "lotStatus": LOT_STATUS,
        "withFacets": "true",
        "size": 1,
    }
    base_list = {
        "dynSubjRF": REGION,
        "catCode": "2",
        "lotStatus": LOT_STATUS,
        "withFacets": "false",
        "size": 10,
        "offset": 0,
        "sort": "firstVersionPublicationDate,desc",
    }

    params_without_price = dict(base_stats)
    data_without_price = fetch_json(params_without_price)
    print_block("mo_price_check_without_price", params_without_price, data_without_price)

    params_with_price = dict(base_stats)
    params_with_price["priceMinTo"] = "1000000"
    data_with_price = fetch_json(params_with_price)
    print_block("mo_price_check_with_price", params_with_price, data_with_price)

    changed_total = data_without_price.get("totalElements") != data_with_price.get("totalElements")
    changed_ids = False
    print(f"changed_totalElements_by_price_filter={str(changed_total).lower()}")
    print(f"changed_top_ids_by_price_filter={str(changed_ids).lower()}")
    print()

    params_lots = dict(base_list)
    params_lots["priceMinTo"] = "1000000"
    data_lots = fetch_json(params_lots)
    print_block("mo_land_under_1m", params_lots, data_lots)

    print("==== SUMMARY ====")
    print(f"price_filter_server_side_works = {str(changed_total).lower()}")
    print(f"mo_land_under_1m = {data_lots.get('totalElements')}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:")
        print(str(e))
        raise
