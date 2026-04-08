"""Safe diagnostics for dynSubjRF and fiasGUID on Torgi lotcards search."""

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
    "lotStatus": "PUBLISHED,APPLICATIONS_SUBMISSION",
    "byFirstVersion": "true",
    "withFacets": "true",
    "size": 10,
    "sort": "firstVersionPublicationDate,desc",
}
TESTS: list[tuple[str, dict[str, Any], str | None]] = [
    ("baseline", {}, None),
    ("mo_only", {"dynSubjRF": "53"}, None),
    (
        "mo_narofominsk_okrug",
        {"dynSubjRF": "53", "fiasGUID": "0d5fdd1b-a7fa-452e-bde7-6f752016d67b"},
        "mo_only",
    ),
    (
        "mo_narofominsk_city",
        {"dynSubjRF": "53", "fiasGUID": "08c78435-6ed8-4d7f-a7ed-3f73e2fa6359"},
        "mo_only",
    ),
    ("kaluga_only", {"dynSubjRF": "44"}, None),
    (
        "kaluga_borovsky_rayon",
        {"dynSubjRF": "44", "fiasGUID": "d3d0c365-e160-43c3-94e3-b593f92f4c22"},
        "kaluga_only",
    ),
    (
        "kaluga_borovsk_city",
        {"dynSubjRF": "44", "fiasGUID": "51d50c38-49c3-47d5-b702-8b601acf2ac5"},
        "kaluga_only",
    ),
]


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get("content")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def shorten(text: Any, limit: int = 120) -> str | None:
    if text is None:
        return None
    value = str(text).replace("\n", " ").replace("\r", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def build_source_url(item: dict[str, Any]) -> str | None:
    external_id = item.get("id") or item.get("lotId") or item.get("noticeNumber")
    if external_id is None:
        return None
    return f"https://torgi.gov.ru/new/public/lots/lot/{external_id}"


def top_ids(items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("id")) for item in items[:10] if item.get("id") is not None]


def top_dates(items: list[dict[str, Any]]) -> list[Any]:
    return [item.get("noticeFirstVersionPublicationDate") for item in items[:10]]


def top_subjects(items: list[dict[str, Any]]) -> list[Any]:
    return [item.get("subjectRFCode") for item in items[:10]]


def top_names(items: list[dict[str, Any]]) -> list[str | None]:
    return [shorten(item.get("lotName") or item.get("title")) for item in items[:3]]


def top_urls(items: list[dict[str, Any]]) -> list[str | None]:
    return [build_source_url(item) for item in items[:3]]


def print_result(
    test_name: str,
    params: dict[str, Any],
    payload: dict[str, Any] | None,
    items: list[dict[str, Any]],
    status_code: int | None,
    changed_vs_baseline: bool | None,
    changed_vs_region_only: bool | None,
    error: Exception | None = None,
) -> None:
    print("==== TEST ====")
    print(f"test_name={test_name}")
    print(f"status_code={status_code if status_code is not None else 'ERROR'}")
    print("request_params=" + json.dumps(params, ensure_ascii=False, sort_keys=True))
    total_elements = payload.get("totalElements") if isinstance(payload, dict) else None
    number_of_elements = payload.get("numberOfElements") if isinstance(payload, dict) else None
    print("totalElements=" + json.dumps(total_elements, ensure_ascii=False))
    print("numberOfElements=" + json.dumps(number_of_elements, ensure_ascii=False))
    print("top10_ids=" + json.dumps(top_ids(items), ensure_ascii=False))
    print("top10_noticeFirstVersionPublicationDate=" + json.dumps(top_dates(items), ensure_ascii=False))
    print("top10_subjectRFCode=" + json.dumps(top_subjects(items), ensure_ascii=False))
    print(
        "changed_vs_baseline="
        + ("null" if changed_vs_baseline is None else ("true" if changed_vs_baseline else "false"))
    )
    print(
        "changed_vs_region_only="
        + ("null" if changed_vs_region_only is None else ("true" if changed_vs_region_only else "false"))
    )
    print("top3_lotName=" + json.dumps(top_names(items), ensure_ascii=False))
    print("top3_source_url=" + json.dumps(top_urls(items), ensure_ascii=False))
    if not items:
        print("content_empty=true")
    else:
        print("content_empty=false")
    if error is not None:
        print(f"error_type={type(error).__name__}")
        print(f"error_message={error}")
    print()


def main() -> int:
    session = requests.Session()
    signatures: dict[str, list[str]] = {}
    conclusions: dict[str, dict[str, Any]] = {}

    for test_name, extra_params, region_parent in TESTS:
        params = dict(BASE_PARAMS)
        params.update(extra_params)

        try:
            response = session.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
            payload = response.json()
            items = extract_items(payload)
            ids = top_ids(items)
            signatures[test_name] = ids

            baseline_ids = signatures.get("baseline", [])
            region_ids = signatures.get(region_parent, []) if region_parent else None
            changed_vs_baseline = ids != baseline_ids if test_name != "baseline" else False
            changed_vs_region_only = ids != region_ids if region_parent else None

            conclusions[test_name] = {
                "status_code": response.status_code,
                "ids": ids,
                "totalElements": payload.get("totalElements") if isinstance(payload, dict) else None,
                "changed_vs_baseline": changed_vs_baseline,
                "changed_vs_region_only": changed_vs_region_only,
            }
            print_result(
                test_name,
                params,
                payload if isinstance(payload, dict) else None,
                items,
                response.status_code,
                changed_vs_baseline,
                changed_vs_region_only,
            )
        except Exception as exc:  # noqa: BLE001
            print_result(test_name, params, None, [], None, None, None, error=exc)

    print("==== CONCLUSION ====")
    dynsubjrf_effect = any(
        conclusions.get(name, {}).get("changed_vs_baseline") for name in ("mo_only", "kaluga_only")
    )
    fias_effect = any(
        conclusions.get(name, {}).get("changed_vs_region_only")
        for name in (
            "mo_narofominsk_okrug",
            "mo_narofominsk_city",
            "kaluga_borovsky_rayon",
            "kaluga_borovsk_city",
        )
    )
    print(f"dynSubjRF_affects_results={'true' if dynsubjrf_effect else 'false'}")
    print(f"fiasGUID_affects_results={'true' if fias_effect else 'false'}")
    print(
        "okrug_vs_city_same_in_moscow="
        + (
            "true"
            if conclusions.get("mo_narofominsk_okrug", {}).get("ids")
            == conclusions.get("mo_narofominsk_city", {}).get("ids")
            else "false"
        )
    )
    print(
        "rayon_vs_city_same_in_kaluga="
        + (
            "true"
            if conclusions.get("kaluga_borovsky_rayon", {}).get("ids")
            == conclusions.get("kaluga_borovsk_city", {}).get("ids")
            else "false"
        )
    )
    print(
        "prefer_next_for_moscow="
        + (
            "GUID района/округа"
            if conclusions.get("mo_narofominsk_okrug", {}).get("totalElements")
            and conclusions.get("mo_narofominsk_city", {}).get("totalElements")
            and conclusions["mo_narofominsk_okrug"]["totalElements"]
            <= conclusions["mo_narofominsk_city"]["totalElements"]
            else "GUID города"
        )
    )
    print(
        "prefer_next_for_kaluga="
        + (
            "GUID района/округа"
            if conclusions.get("kaluga_borovsky_rayon", {}).get("totalElements")
            and conclusions.get("kaluga_borovsk_city", {}).get("totalElements")
            and conclusions["kaluga_borovsky_rayon"]["totalElements"]
            <= conclusions["kaluga_borovsk_city"]["totalElements"]
            else "GUID города"
        )
    )
    print(
        "future_combinations="
        + json.dumps(
            [
                {"dynSubjRF": "53", "fiasGUID": "0d5fdd1b-a7fa-452e-bde7-6f752016d67b"},
                {"dynSubjRF": "53", "fiasGUID": "08c78435-6ed8-4d7f-a7ed-3f73e2fa6359"},
                {"dynSubjRF": "44", "fiasGUID": "d3d0c365-e160-43c3-94e3-b593f92f4c22"},
                {"dynSubjRF": "44", "fiasGUID": "51d50c38-49c3-47d5-b702-8b601acf2ac5"},
            ],
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
