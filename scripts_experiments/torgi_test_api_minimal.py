"""Minimal API connectivity test for torgi.gov.ru."""

from __future__ import annotations

import time
import requests


URL = "https://torgi.gov.ru/new/api/public/lotcards/search"
PARAMS = {
    "size": 1,
    "catCode": 2,
    "lotStatus": "PUBLISHED",
}
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://torgi.gov.ru/new/public/lots/reg",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def main() -> int:
    session = requests.Session()
    last_error = None

    for _ in range(3):
        try:
            start = time.time()
            response = session.get(URL, params=PARAMS, headers=HEADERS, timeout=30)
            elapsed = time.time() - start
            response.raise_for_status()
            payload = response.json() if isinstance(response.json(), dict) else {}
            items = payload.get("content") if isinstance(payload, dict) else []
            if not isinstance(items, list):
                items = []
            first = items[0] if items else {}
            print("RESULT:")
            print(f"status_code={response.status_code}")
            print(f"response_time={elapsed:.3f}")
            print(f"totalElements={payload.get('totalElements')}")
            print(f"first_id={first.get('id')}")
            print(f"first_etp={first.get('etpCode')}")
            return 0
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    if last_error is not None:
        print("RESULT:")
        print("status_code=null")
        print("response_time=null")
        print("totalElements=null")
        print("first_id=null")
        print("first_etp=null")
        print()
        print("ERROR:")
        print(f"error_type={type(last_error).__name__}")
        print(f"error_text={last_error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
