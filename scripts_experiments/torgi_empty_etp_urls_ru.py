#!/usr/bin/env python3
import json
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
LOT_URL = "https://torgi.gov.ru/new/public/lots/lot/{lot_id}"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}
TIMEOUT_SECONDS = 30
RETRIES = 3
RETRY_SLEEP_SECONDS = 2.5
REGION = "54"
LOT_STATUS = "PUBLISHED,APPLICATIONS_SUBMISSION"


def fetch_page(offset: int, size: int = 10):
    params = {
        "dynSubjRF": REGION,
        "catCode": "2",
        "lotStatus": LOT_STATUS,
        "size": size,
        "offset": offset,
        "sort": "firstVersionPublicationDate,desc",
        "withFacets": "false",
    }
    url = f"{BASE_URL}?{urlencode(params)}"
    last_error = None

    for attempt in range(1, RETRIES + 1):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data
        except Exception as e:
            last_error = e
            if attempt < RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS)

    raise last_error


def etp_is_empty(item):
    val = item.get("etpCode")
    return val is None or not str(val).strip()


def get_lot_id(item):
    return item.get("id") or item.get("lotId") or item.get("noticeNumber")


def main():
    found = []
    seen_ids = set()

    for offset in (0, 10):
        data = fetch_page(offset=offset, size=10)
        content = data.get("content") or []
        for item in content:
            if not etp_is_empty(item):
                continue
            lot_id = get_lot_id(item)
            if not lot_id or lot_id in seen_ids:
                continue
            seen_ids.add(lot_id)
            found.append(LOT_URL.format(lot_id=lot_id))
            if len(found) >= 5:
                break
        if len(found) >= 5:
            break

    print("RESULT:")
    if found:
        for url in found[:5]:
            print(url)
    else:
        print("Лоты с пустым ETP не найдены в первых 20 записях.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:")
        print(str(e))
        sys.exit(1)
