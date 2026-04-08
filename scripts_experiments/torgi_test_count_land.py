"""Safe diagnostics for counting land lots under 1,000,000 RUB by FIAS."""

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
BASE_PARAMS = {
    "lotStatus": "APPLICATIONS_SUBMISSION",
    "catCode": "2",
    "priceMinTo": "1000000",
    "byFirstVersion": "true",
    "withFacets": "true",
    "size": 10,
    "sort": "firstVersionPublicationDate,desc",
}

TESTS = [
    (
        "narofominsk_land_under_1m",
        {"fiasGUID": "0d5fdd1b-a7fa-452e-bde7-6f752016d67b"},
    ),
    (
        "borovsky_land_under_1m",
        {"fiasGUID": "d3d0c365-e160-43c3-94e3-b593f92f4c22"},
    ),
]


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get("content")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def build_source_url(item: dict[str, Any]) -> str | None:
    external_id = item.get("id") or item.get("lotId") or item.get("noticeNumber")
    if external_id is None:
        return None
    return f"https://torgi.gov.ru/new/public/lots/lot/{external_id}"


def main() -> int:
    session = requests.Session()
    totals: dict[str, int | None] = {}

    for test_name, extra_params in TESTS:
        params = dict(BASE_PARAMS)
        params.update(extra_params)

        try:
            response = session.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
            payload = response.json()
            items = extract_items(payload)
            total_elements = payload.get("totalElements") if isinstance(payload, dict) else None
            number_of_elements = payload.get("numberOfElements") if isinstance(payload, dict) else None

            print("==== TEST ====")
            print(f"test_name={test_name}")
            print(f"status_code={response.status_code}")
            print("request_params=" + json.dumps(params, ensure_ascii=False, sort_keys=True))
            print("totalElements=" + json.dumps(total_elements, ensure_ascii=False))
            print("numberOfElements=" + json.dumps(number_of_elements, ensure_ascii=False))
            print(
                "top10_ids="
                + json.dumps([item.get("id") for item in items[:10]], ensure_ascii=False)
            )
            print(
                "top10_lotName="
                + json.dumps([item.get("lotName") for item in items[:10]], ensure_ascii=False)
            )
            print(
                "top10_priceMin="
                + json.dumps([item.get("priceMin") for item in items[:10]], ensure_ascii=False)
            )
            print(
                "top10_noticeFirstVersionPublicationDate="
                + json.dumps(
                    [item.get("noticeFirstVersionPublicationDate") for item in items[:10]],
                    ensure_ascii=False,
                )
            )
            print(
                "top10_source_url="
                + json.dumps([build_source_url(item) for item in items[:10]], ensure_ascii=False)
            )
            print()

            totals[test_name] = total_elements if isinstance(total_elements, int) else None
        except Exception as exc:  # noqa: BLE001
            print("==== TEST ====")
            print(f"test_name={test_name}")
            print("status_code=ERROR")
            print("request_params=" + json.dumps(params, ensure_ascii=False, sort_keys=True))
            print("totalElements=null")
            print("numberOfElements=null")
            print("top10_ids=[]")
            print("top10_lotName=[]")
            print("top10_priceMin=[]")
            print("top10_noticeFirstVersionPublicationDate=[]")
            print("top10_source_url=[]")
            print(f"error_type={type(exc).__name__}")
            print(f"error_message={exc}")
            print()
            totals[test_name] = None

    print("==== SUMMARY ====")
    narofominsk = totals.get("narofominsk_land_under_1m")
    borovsky = totals.get("borovsky_land_under_1m")
    total_two = None
    if isinstance(narofominsk, int) and isinstance(borovsky, int):
        total_two = narofominsk + borovsky
    print(f"narofominsk_land_under_1m = {narofominsk}")
    print(f"borovsky_land_under_1m = {borovsky}")
    print(f"total_two_regions = {total_two}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
