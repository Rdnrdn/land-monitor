"""Safe diagnostics for FIAS hierarchy lookup on torgi.gov.ru."""

from __future__ import annotations

import json
from typing import Any

import requests


URL = "https://torgi.gov.ru/new/fias/public/address"
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
QUERIES = [
    "московская",
    "наро",
    "наро-фоминск",
    "обл московская, г.о. наро-фоминский",
    "обл московская, г.о. наро-фоминский, г наро-фоминск",
    "калужская",
    "боро",
    "боровск",
    "калужская обл, боровский район",
    "калужская обл, боровский район, г боровск",
]


def normalize_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("content", "items", "results", "list", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def pick_first(item: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", []):
            return value
    return None


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "guid": pick_first(item, ["guid", "fiasGUID", "fiasGuid", "aoGuid", "objectGuid"]),
        "name": pick_first(item, ["name", "formalName", "fullName", "shortName"]),
        "address": pick_first(item, ["address", "fullAddress", "text", "displayName", "path", "value"]),
        "type_or_level": pick_first(
            item,
            ["type", "level", "objectLevel", "addrObjLevel", "shortTypeName", "aoLevel"],
        ),
        "munUid": pick_first(item, ["munUid", "munUID"]),
    }


def print_query_result(query: str, status_code: int, items: list[dict[str, Any]]) -> None:
    print("==== QUERY ====")
    print(f"query={query}")
    print(f"status_code={status_code}")
    print(f"count={len(items)}")
    print("top5=")
    for item in items[:5]:
        print(json.dumps(compact_item(item), ensure_ascii=False))
    print()


def infer_levels(found: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    regions: list[dict[str, Any]] = []
    districts: list[dict[str, Any]] = []
    cities: list[dict[str, Any]] = []

    for query, items in found.items():
        for item in items[:5]:
            compact = compact_item(item)
            blob = json.dumps(compact, ensure_ascii=False).lower()
            name = str(compact.get("name") or "").lower()
            address = str(compact.get("address") or "").lower()

            if any(token in blob for token in ["область", "обл"]) and compact not in regions:
                regions.append({"query": query, **compact})

            if any(token in blob for token in ["район", "р-н", "городской округ", "г.о.", "округ"]) and compact not in districts:
                districts.append({"query": query, **compact})

            if (
                any(token in address for token in [" г ", "город", "г. "])
                or any(token in name for token in ["наро-фоминск", "боровск"])
            ) and compact not in cities:
                cities.append({"query": query, **compact})

    return {
        "regions": regions[:10],
        "districts": districts[:10],
        "cities": cities[:10],
    }


def main() -> int:
    session = requests.Session()
    found: dict[str, list[dict[str, Any]]] = {}

    for query in QUERIES:
        response = session.get(URL, params={"query": query}, headers=HEADERS, timeout=TIMEOUT)
        try:
            payload = response.json()
        except ValueError:
            payload = []
        items = normalize_items(payload)
        found[query] = items
        print_query_result(query, response.status_code, items)

    inferred = infer_levels(found)
    print("==== CONCLUSION ====")
    print("region_like=")
    for item in inferred["regions"][:5]:
        print(json.dumps(item, ensure_ascii=False))
    print("district_or_urban_okrug_like=")
    for item in inferred["districts"][:5]:
        print(json.dumps(item, ensure_ascii=False))
    print("city_like=")
    for item in inferred["cities"][:5]:
        print(json.dumps(item, ensure_ascii=False))
    print("guids_to_verify_in_lotcards_search=")
    for bucket in ("regions", "districts", "cities"):
        for item in inferred[bucket][:8]:
            print(json.dumps({"query": item["query"], "guid": item.get("guid"), "name": item.get("name")}, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
