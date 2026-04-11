#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import time
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from django.db import transaction


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
SRC_DIR = ROOT_DIR / "src"
OUTPUT_DIR = ROOT_DIR / ".local" / "diagnostics"

sys.path.insert(0, str(WEB_DIR))
sys.path.insert(0, str(SRC_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webapp.settings")

import django  # noqa: E402

django.setup()

from lots.models import Lot, Region  # noqa: E402


BASE_URL = "https://torgi.gov.ru/new/api/public/lotcards"
REGION_SLUG = "moskovskaya-oblast"
LIMIT = 100
REQUEST_DELAY_SECONDS = 0.7
TIMEOUT_SECONDS = 30
RETRY_DELAYS_SECONDS = (3.0, 7.0)

FIELDS = (
    "estateAddress",
    "deposit",
    "auctionStartDate",
    "biddStartTime",
    "biddEndTime",
    "typeTransaction",
    "etpUrl",
    "subjectRFCode",
    "point",
    "lotAttachments",
    "noticeAttachments",
    "attributes",
)

LOW_SIGNAL_VALUES = {
    "согласно извещению",
    "согласно извещению о проведении аукциона",
    "не указано",
    "отсутствует",
    "-",
    "—",
}

ATTRIBUTE_LABELS = {
    "encumbrances": "Обременения",
    "deposit_rules": "Срок и порядок внесения задатка",
    "inspection_rules": "Порядок ознакомления с имуществом",
    "contract_sign_period": "Срок заключения договора",
    "contract_terms": "Условия договора",
}


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "value", "fullName"):
            cleaned = clean_text(value.get(key))
            if cleaned:
                return cleaned
        return None
    if isinstance(value, list):
        parts = [clean_text(item) for item in value]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None

    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if not cleaned or cleaned.casefold() in {"none", "null"}:
        return None
    return cleaned


def has_value(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return bool(clean_text(value))


def is_useful_text(value: Any) -> bool:
    cleaned = clean_text(value)
    return bool(cleaned and cleaned.casefold() not in LOW_SIGNAL_VALUES)


def attribute_key(full_name: str) -> str | None:
    normalized = full_name.casefold()
    if "обременения реализуемого имущества" in normalized:
        return "encumbrances"
    if "срок и порядок внесения задатка" in normalized:
        return "deposit_rules"
    if "порядок ознакомления с имуществом" in normalized:
        return "inspection_rules"
    if "ознаком" in normalized and ("имуществ" in normalized or "схем" in normalized):
        return "inspection_rules"
    if "срок заключения договора" in normalized:
        return "contract_sign_period"
    if "условия договора, заключаемого по результатам торгов" in normalized:
        return "contract_terms"
    return None


def useful_attributes(payload: dict[str, Any]) -> dict[str, str]:
    attributes = payload.get("attributes")
    if not isinstance(attributes, list):
        return {}

    result: dict[str, str] = {}
    for item in attributes:
        if not isinstance(item, dict):
            continue
        full_name = clean_text(item.get("fullName"))
        if not full_name:
            continue
        key = attribute_key(full_name)
        value = clean_text(item.get("value"))
        if key and key not in result and is_useful_text(value):
            result[key] = value or ""
    return result


def fetch_lotcard(session: requests.Session, source_lot_id: str) -> tuple[int | None, int, dict[str, Any] | None, str | None]:
    started = time.perf_counter()
    attempts = len(RETRY_DELAYS_SECONDS) + 1
    last_status_code: int | None = None
    last_error: str | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(f"{BASE_URL}/{source_lot_id}", timeout=TIMEOUT_SECONDS)
            last_status_code = response.status_code
            if response.status_code in {502, 503, 504} and attempt < attempts:
                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                continue
            if response.status_code != 200:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return response.status_code, elapsed_ms, None, f"http_{response.status_code}"
            try:
                payload = response.json()
            except ValueError:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return response.status_code, elapsed_ms, None, "invalid_json"
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if not isinstance(payload, dict):
                return response.status_code, elapsed_ms, None, "json_not_dict"
            return response.status_code, elapsed_ms, payload, None
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                continue
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return last_status_code, elapsed_ms, None, last_error

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return last_status_code, elapsed_ms, None, last_error or "unknown_error"


def latest_mo_lots(*, only_missing: bool) -> list[Lot]:
    region = Region.objects.get(slug=REGION_SLUG)
    queryset = (
        Lot.objects.filter(region_ref=region, source_lot_id__isnull=False)
        .exclude(source_lot_id="")
        .order_by("-id")[:LIMIT]
    )
    lots = list(queryset)
    if only_missing:
        lots = [
            lot
            for lot in lots
            if not (isinstance(lot.raw_data, dict) and isinstance(lot.raw_data.get("lotcard"), dict))
        ]
    return lots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch lotcards for the latest Moscow Oblast lots and save local raw_data snapshots.",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Process only selected latest lots that do not have raw_data['lotcard'] yet.",
    )
    return parser.parse_args()


def payload_field_flags(payload: dict[str, Any]) -> dict[str, bool]:
    flags = {field: has_value(payload.get(field)) for field in FIELDS}
    point = payload.get("point")
    flags["point"] = bool(
        isinstance(point, dict)
        and point.get("lat") not in (None, "")
        and point.get("lon") not in (None, "")
    )
    return flags


def lotcard_snapshot(payload: dict[str, Any], *, source_lot_id: str, status_code: int | None) -> dict[str, Any]:
    snapshot = {
        field: payload.get(field)
        for field in FIELDS
        if field != "attributes"
    }
    snapshot["attributes"] = payload.get("attributes")
    snapshot["lotDescription"] = payload.get("lotDescription")
    snapshot["_meta"] = {
        "source": "torgi.gov.ru lotcards",
        "source_lot_id": source_lot_id,
        "status_code": status_code,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    return snapshot


def save_lotcard_snapshot(lot: Lot, snapshot: dict[str, Any]) -> None:
    raw_data = dict(lot.raw_data or {})
    raw_data["lotcard"] = snapshot
    Lot.objects.filter(pk=lot.pk).update(raw_data=raw_data)


def richness_score(flags: dict[str, bool], attrs: dict[str, str]) -> int:
    return sum(1 for value in flags.values() if value) + len(attrs)


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def main() -> None:
    args = parse_args()
    lots = latest_mo_lots(only_missing=args.only_missing)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"lotcards_mo_enrichment_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "land-monitor-local-lotcard-enrichment-check/1.0",
        }
    )

    print(f"region_slug={REGION_SLUG}")
    print("selection=latest_by_id_desc")
    print(f"limit={LIMIT}")
    print(f"selected_lots={len(lots)}")
    print(f"only_missing={args.only_missing}")
    print(f"request_delay_seconds={REQUEST_DELAY_SECONDS}")
    print(f"retry_delays_seconds={RETRY_DELAYS_SECONDS}")
    print(f"output_path={output_path}")

    coverage: Counter[str] = Counter()
    attribute_coverage: Counter[str] = Counter()
    status_codes: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    saved_count = 0

    for index, lot in enumerate(lots, start=1):
        status_code, elapsed_ms, payload, error = fetch_lotcard(session, lot.source_lot_id)
        status_codes[str(status_code or "error")] += 1
        print(
            f"[{index}/{len(lots)}] lot_id={lot.id} source_lot_id={lot.source_lot_id} "
            f"status={status_code} elapsed_ms={elapsed_ms} error={error or '-'}"
        )

        flags: dict[str, bool] = {}
        attrs: dict[str, str] = {}
        if payload is not None:
            coverage["success"] += 1
            flags = payload_field_flags(payload)
            attrs = useful_attributes(payload)
            snapshot = lotcard_snapshot(
                payload,
                source_lot_id=lot.source_lot_id,
                status_code=status_code,
            )
            with transaction.atomic():
                save_lotcard_snapshot(lot, snapshot)
            saved_count += 1
            for field, present in flags.items():
                if present:
                    coverage[field] += 1
            for key in attrs:
                attribute_coverage[key] += 1
        else:
            coverage["failed"] += 1

        rows.append(
            {
                "lot_id": lot.id,
                "source_lot_id": lot.source_lot_id,
                "title": lot.title,
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "error": error,
                "field_flags": flags,
                "useful_attributes": attrs,
                "richness_score": richness_score(flags, attrs),
                "lotcard": payload,
            }
        )

        if index < len(lots):
            time.sleep(REQUEST_DELAY_SECONDS)

    summary = {
        "region_slug": REGION_SLUG,
        "selection": "region_ref.slug=moskovskaya-oblast, source_lot_id present, order_by=-id",
        "limit": LIMIT,
        "selected_lots": len(lots),
        "only_missing": args.only_missing,
        "request_delay_seconds": REQUEST_DELAY_SECONDS,
        "retry_delays_seconds": RETRY_DELAYS_SECONDS,
        "success": coverage["success"],
        "failed": coverage["failed"],
        "saved_to_db": saved_count,
        "status_codes": dict(status_codes),
        "field_coverage": {field: coverage[field] for field in FIELDS},
        "attribute_coverage": {
            key: {
                "label": ATTRIBUTE_LABELS[key],
                "count": attribute_coverage[key],
            }
            for key in ATTRIBUTE_LABELS
        },
    }

    richest = sorted(rows, key=lambda row: row["richness_score"], reverse=True)[:5]
    samples = [
        {
            "lot_id": row["lot_id"],
            "source_lot_id": row["source_lot_id"],
            "title": row["title"],
            "richness_score": row["richness_score"],
            "fields": [field for field, present in row["field_flags"].items() if present],
            "attributes": {
                key: ATTRIBUTE_LABELS[key]
                for key in row["useful_attributes"]
            },
        }
        for row in richest
    ]

    report = {
        "summary": summary,
        "richest_samples": samples,
        "results": rows,
    }
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )

    print("=" * 100)
    print("summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("richest_samples")
    print(json.dumps(samples, ensure_ascii=False, indent=2))
    print(f"saved_to={output_path}")


if __name__ == "__main__":
    main()
