"""Fetch 10 lot URLs with empty etpCode for dynSubjRF=54."""

from __future__ import annotations

import requests


URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
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
    "dynSubjRF": "54",
    "catCode": "2",
    "lotStatus": "PUBLISHED,APPLICATIONS_SUBMISSION",
    "size": 10,
    "offset": 0,
    "sort": "firstVersionPublicationDate,desc",
    "withFacets": "false",
}


def main() -> int:
    session = requests.Session()
    found: list[str] = []
    offset = 0
    total_elements: int | None = None

    while len(found) < 10:
        if total_elements is not None and offset >= total_elements:
            break
        params = dict(BASE_PARAMS)
        params["offset"] = offset
        response = session.get(URL, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and total_elements is None:
            total_raw = payload.get("totalElements")
            if isinstance(total_raw, int):
                total_elements = total_raw
        items = payload.get("content") if isinstance(payload, dict) else []
        if not isinstance(items, list) or not items:
            break

        for item in items:
            if not isinstance(item, dict):
                continue
            etp = item.get("etpCode")
            if etp is not None and str(etp).strip() != "":
                continue
            lot_id = item.get("id")
            if not lot_id:
                continue
            url = f"https://torgi.gov.ru/new/public/lots/lot/{lot_id}"
            if url not in found:
                found.append(url)
                if len(found) >= 10:
                    break

        offset += 10

    print("RESULT:")
    for idx, url in enumerate(found[:10], start=1):
        print(f"{idx}. {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
