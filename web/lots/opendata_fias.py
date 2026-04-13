from __future__ import annotations

from typing import Any


FIAS_LEVEL_CODES = (3, 5, 6)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _level_code(value: Any) -> int | None:
    raw_code = _as_dict(_as_dict(value).get("level")).get("code")
    try:
        return int(raw_code)
    except (TypeError, ValueError):
        return None


def extract_fias_levels(estate_address_fias: Any) -> dict[str, str | None]:
    address_by_fias = _as_dict(_as_dict(estate_address_fias).get("addressByFIAS"))
    hierarchy_objects = address_by_fias.get("hierarchyObjects")
    result: dict[str, str | None] = {
        "fias_level_3_guid": None,
        "fias_level_3_name": None,
        "fias_level_5_guid": None,
        "fias_level_5_name": None,
        "fias_level_6_guid": None,
        "fias_level_6_name": None,
    }
    if not isinstance(hierarchy_objects, list):
        return result

    for item in hierarchy_objects:
        if not isinstance(item, dict):
            continue
        level_code = _level_code(item)
        if level_code not in FIAS_LEVEL_CODES:
            continue
        guid_key = f"fias_level_{level_code}_guid"
        name_key = f"fias_level_{level_code}_name"
        if result[guid_key] or result[name_key]:
            continue
        result[guid_key] = _clean_text(item.get("guid"))
        result[name_key] = _clean_text(item.get("name"))

    return result
