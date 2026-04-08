"""Safe diagnostics for date filtering on the public Torgi.gov lot list API."""

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
    "page": 0,
    "size": 5,
    "sort": "firstVersionPublicationDate,desc",
}


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    content = payload.get("content")
    if isinstance(content, list):
        return [item for item in content if isinstance(item, dict)]
    return []


def summarize_items(items: list[dict[str, Any]]) -> tuple[list[str | None], list[str]]:
    dates = [item.get("noticeFirstVersionPublicationDate") for item in items[:3]]
    ids = [str(item.get("id")) for item in items[:3] if item.get("id") is not None]
    return dates, ids


def make_signature(items: list[dict[str, Any]]) -> list[tuple[Any, Any]]:
    return [
        (item.get("id"), item.get("noticeFirstVersionPublicationDate"))
        for item in items[:5]
        if isinstance(item, dict)
    ]


def print_case(
    test_name: str,
    params: dict[str, Any],
    response: requests.Response | None,
    items: list[dict[str, Any]],
    changed_vs_baseline: bool | None,
    error: Exception | None = None,
) -> None:
    print("==== TEST ====")
    print(f"test_name={test_name}")
    if response is not None:
        print(f"status_code={response.status_code}")
    else:
        print("status_code=ERROR")
    print("request_params=" + json.dumps(params, ensure_ascii=False, sort_keys=True))
    if error is not None:
        print(f"error_type={type(error).__name__}")
        print(f"error_message={error}")
    print(f"content_count={len(items)}")
    dates, ids = summarize_items(items)
    print("noticeFirstVersionPublicationDate_top3=" + json.dumps(dates, ensure_ascii=False))
    print("lot_ids_top3=" + json.dumps(ids, ensure_ascii=False))
    if changed_vs_baseline is None:
        print("changed_vs_baseline=null")
    else:
        print(f"changed_vs_baseline={'true' if changed_vs_baseline else 'false'}")
    print()


def main() -> int:
    session = requests.Session()

    tests: list[tuple[str, dict[str, Any]]] = [
        ("baseline", {}),
        ("firstVersionPublicationDateFrom_date", {"firstVersionPublicationDateFrom": "2026-04-01"}),
        ("firstVersionPublicationDateTo_date", {"firstVersionPublicationDateTo": "2026-04-01"}),
        ("createDateFrom_datetime", {"createDateFrom": "2026-04-01T00:00:00"}),
        ("createDateTo_datetime", {"createDateTo": "2026-04-01T00:00:00"}),
        (
            "noticeFirstVersionPublicationDateFrom_zulu",
            {"noticeFirstVersionPublicationDateFrom": "2026-04-01T00:00:00Z"},
        ),
        (
            "noticeFirstVersionPublicationDateTo_zulu",
            {"noticeFirstVersionPublicationDateTo": "2026-04-01T00:00:00Z"},
        ),
        ("publishDateFrom_date", {"publishDateFrom": "2026-04-01"}),
        ("publishDateTo_date", {"publishDateTo": "2026-04-01"}),
    ]

    baseline_signature: list[tuple[Any, Any]] | None = None
    working_params: list[str] = []
    unchanged_params: list[str] = []
    failed_params: list[str] = []

    for test_name, extra_params in tests:
        params = dict(BASE_PARAMS)
        params.update(extra_params)

        try:
            response = session.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
            items = extract_items(response.json()) if response.headers.get("content-type", "").find("json") >= 0 else []
            signature = make_signature(items)

            if test_name == "baseline":
                baseline_signature = signature
                changed_vs_baseline = False
            else:
                changed_vs_baseline = signature != (baseline_signature or [])
                if response.status_code == 200 and changed_vs_baseline:
                    working_params.append(next(iter(extra_params)))
                elif response.status_code == 200:
                    unchanged_params.append(next(iter(extra_params)))
                else:
                    failed_params.append(next(iter(extra_params)))

            print_case(test_name, params, response, items, changed_vs_baseline)
        except Exception as exc:  # noqa: BLE001
            if test_name != "baseline":
                failed_params.append(next(iter(extra_params)))
            print_case(test_name, params, None, [], None, error=exc)

    print("==== CONCLUSION ====")
    print("working_params=" + json.dumps(working_params, ensure_ascii=False))
    print("unchanged_params=" + json.dumps(unchanged_params, ensure_ascii=False))
    print("failed_params=" + json.dumps(failed_params, ensure_ascii=False))
    if working_params:
        print("api_date_filtering=looks_supported_for_some_params")
    else:
        print("api_date_filtering=no_clear_evidence_from_safe_tests")
    if unchanged_params and not working_params:
        print("fallback=paginate_and_stop_when_noticeFirstVersionPublicationDate_becomes_older_than_target")
    else:
        print("fallback=optional_paginate_and_stop_by_noticeFirstVersionPublicationDate_for_safety")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
