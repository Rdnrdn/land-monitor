"""Diagnostic checks for the public lotcards search endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from land_monitor.parsers.torgi_gov import TorgiGovParser


URL = TorgiGovParser.search_url
TIMEOUT = 15
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": "https://torgi.gov.ru/new/public/lots/reg",
    "User-Agent": TorgiGovParser.user_agent,
}
MINIMAL_PAYLOAD = {
    "page": 0,
    "size": 5,
    "sort": "firstVersionPublicationDate,desc",
}


def body_sample(response: requests.Response) -> str:
    return response.text[:300].replace("\n", " ").replace("\r", " ")


def print_result(name: str, response: requests.Response | None = None, error: Exception | None = None) -> None:
    print(f"==== {name} ====")
    print(f"URL: {URL}")
    if response is not None:
        print(f"Status code: {response.status_code}")
        print("Response headers:")
        for key, value in response.headers.items():
            print(f"  {key}: {value}")
        print(f"Body sample: {body_sample(response)}")

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            print(f"Top-level fields: {', '.join(sorted(payload.keys()))}")
            items = extract_items(payload)
            print_examples(items)
        elif isinstance(payload, list):
            print("Top-level fields: <list response>")
            print_examples([item for item in payload if isinstance(item, dict)])
    else:
        print(f"Exception: {type(error).__name__}")
        print(f"Message: {error}")
    print()


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "items", "results", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def print_examples(items: list[dict[str, Any]]) -> None:
    if not items:
        print("Example objects: []")
        return
    print("Example objects:")
    for item in items[:3]:
        print(json.dumps(item, ensure_ascii=False, indent=2)[:800])


def run_case(name: str, method: str, **kwargs: Any) -> None:
    try:
        response = requests.request(method, URL, headers=HEADERS, timeout=TIMEOUT, **kwargs)
        print_result(name, response=response)
    except Exception as exc:  # noqa: BLE001
        print_result(name, error=exc)


def main() -> int:
    run_case("GET", "GET", params=MINIMAL_PAYLOAD)
    run_case("POST without body", "POST")
    run_case("POST with minimal JSON payload", "POST", json=MINIMAL_PAYLOAD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
