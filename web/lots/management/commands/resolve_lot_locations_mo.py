"""Resolve municipality and settlement names for Moscow region lots."""

from __future__ import annotations

import re
from typing import Any

from django.core.management.base import BaseCommand
from sqlalchemy import or_

from land_monitor.db import SessionLocal
from land_monitor.models import Lot, Notice


MUNICIPALITY_HINTS = (
    "городской округ",
    "г.о.",
    "г. о.",
    "муниципальный округ",
    "м.о.",
    "м. о.",
    "район",
    "р-н",
)

SETTLEMENT_PREFIXES = (
    "г.",
    "д.",
    "с.",
    "п.",
    "пос.",
    "пгт",
    "рп",
    "мкр",
    "снт",
    "тер.",
)

MUNICIPALITY_PATTERNS = [
    re.compile(r"(?:г\.о\.|г\. о\.|городской округ)\s*([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"([А-ЯЁ][А-ЯЁа-яё\- ]+)\s*(?:г\.о\.|г\. о\.|городской округ)", re.IGNORECASE),
    re.compile(r"(?:м\.о\.|м\. о\.|муниципальный округ)\s*([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"([А-ЯЁ][А-ЯЁа-яё\- ]+)\s*(?:м\.о\.|м\. о\.|муниципальный округ)", re.IGNORECASE),
    re.compile(r"([А-ЯЁ][А-ЯЁа-яё\- ]+)\s*(?:район|р-н)", re.IGNORECASE),
    re.compile(r"(?:район|р-н)\s*([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
]

SETTLEMENT_PATTERNS = [
    re.compile(r"\bг\.\s*(?!о\b)([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bгород\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bд\.\s*([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bдеревня\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bс\.\s*([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bсело\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bпгт\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bрп\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bрабочий\s+пос[её]лок\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bпос\.?\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bпос[её]лок\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bп\.\s*([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bмкр\.?\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bснт\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
    re.compile(r"\bтер\.?\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)", re.IGNORECASE),
]

ADDRESS_KEYS = (
    "address",
    "адрес",
    "местоп",
    "располож",
    "location",
    "place",
)


def _extract_strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    strings: list[tuple[str, str]] = []
    stack: list[tuple[Any, str]] = [(value, path)]
    while stack:
        current, current_path = stack.pop()
        if isinstance(current, str):
            strings.append((current, current_path))
            continue
        if isinstance(current, dict):
            for key, val in current.items():
                next_path = f"{current_path}.{key}" if current_path else str(key)
                stack.append((val, next_path))
            continue
        if isinstance(current, list):
            for idx, item in enumerate(current):
                next_path = f"{current_path}[{idx}]"
                stack.append((item, next_path))
            continue
    return strings


def _address_strings_from_raw(raw: Any) -> list[str]:
    if not raw:
        return []
    strings = _extract_strings(raw)
    results: list[str] = []
    for text, path in strings:
        path_l = path.lower()
        if any(key in path_l for key in ADDRESS_KEYS):
            results.append(text)
    return results


def _address_strings_from_notice(raw: Any) -> list[str]:
    if not isinstance(raw, dict):
        return []
    results: list[str] = []
    attrs = raw.get("attributes")
    if isinstance(attrs, list):
        for attr in attrs:
            if not isinstance(attr, dict):
                continue
            name = str(attr.get("name") or attr.get("fullName") or "").lower()
            if any(k in name for k in ADDRESS_KEYS):
                for key in ("value", "valueText", "text", "name"):
                    value = attr.get(key)
                    if isinstance(value, str):
                        results.append(value)
    results.extend(_address_strings_from_raw(raw))
    return results


def _all_strings_from_raw(raw: Any) -> list[str]:
    if not raw:
        return []
    return [text for text, _ in _extract_strings(raw)]


def _normalize_municipality(name: str, kind: str) -> str:
    cleaned = " ".join(name.strip().split())
    if kind == "городской округ":
        return f"Городской округ {cleaned}"
    if kind == "муниципальный округ":
        return f"Муниципальный округ {cleaned}"
    if kind == "район":
        return f"{cleaned} район"
    return cleaned


def _detect_municipality(text: str) -> str | None:
    for pattern in MUNICIPALITY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = match.group(1)
        snippet = match.group(0).lower()
        if "городской округ" in snippet or "г.о" in snippet:
            return _normalize_municipality(name, "городской округ")
        if "муниципальный округ" in snippet or "м.о" in snippet:
            return _normalize_municipality(name, "муниципальный округ")
        if "район" in snippet or "р-н" in snippet:
            return _normalize_municipality(name, "район")
        return _normalize_municipality(name, "")
    return None


def _detect_settlement(text: str) -> str | None:
    for pattern in SETTLEMENT_PATTERNS:
        match = pattern.search(text)
        if match:
            name = match.group(1).strip()
            name = " ".join(name.split())
            snippet = match.group(0).lower()
            if "город" in snippet or "г." in snippet:
                return f"г. {name}"
            if "деревня" in snippet or "д." in snippet:
                return f"д. {name}"
            if "село" in snippet or "с." in snippet:
                return f"с. {name}"
            if "пгт" in snippet:
                return f"пгт {name}"
            if "рп" in snippet or "рабочий поселок" in snippet or "рабочий посёлок" in snippet:
                return f"рп {name}"
            if "мкр" in snippet:
                return f"мкр {name}"
            if "снт" in snippet:
                return f"снт {name}"
            if "тер" in snippet:
                return f"тер. {name}"
            if "пос" in snippet or "поселок" in snippet or "посёлок" in snippet or "п." in snippet:
                return f"п. {name}"
            return name
    return None


class Command(BaseCommand):
    help = "Resolve municipality and settlement names for Moscow region lots."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        batch_size = int(options["batch_size"])
        total_processed = 0
        municipality_filled = 0
        settlement_filled = 0

        db = SessionLocal()
        try:
            last_id = 0
            while True:
                lots = (
                    db.query(Lot)
                    .filter(or_(Lot.settlement_name.is_(None), Lot.settlement_name == ""))
                    .filter(Lot.id > last_id)
                    .order_by(Lot.id.asc())
                    .limit(batch_size)
                    .all()
                )
                if not lots:
                    break

                notice_numbers = [lot.notice_number for lot in lots if lot.notice_number]
                notices_map = {}
                if notice_numbers:
                    notices = (
                        db.query(Notice)
                        .filter(Notice.notice_number.in_(notice_numbers))
                        .all()
                    )
                    notices_map = {n.notice_number: n for n in notices}

                for lot in lots:
                    address_blob = ""
                    if lot.address:
                        address_blob = lot.address
                    else:
                        raw_texts = _address_strings_from_raw(lot.raw_data)
                        address_blob = " ".join(raw_texts)

                    notice_texts: list[str] = []
                    if lot.notice_number and lot.notice_number in notices_map:
                        notice_raw = notices_map[lot.notice_number].raw_data
                        notice_texts = _address_strings_from_notice(notice_raw)

                    fallback = " ".join(
                        [text for text in [lot.title or "", lot.description or ""] if text]
                    )

                    text_blob = " ".join([address_blob, " ".join(notice_texts), fallback]).strip()
                    settlement_blob = " ".join(
                        [
                            address_blob,
                            " ".join(_all_strings_from_raw(lot.raw_data)),
                            " ".join(_all_strings_from_raw(
                                notices_map[lot.notice_number].raw_data
                            )) if lot.notice_number and lot.notice_number in notices_map else "",
                            fallback,
                        ]
                    ).strip()

                    municipality = _detect_municipality(text_blob)
                    settlement = _detect_settlement(settlement_blob)

                    if municipality and not lot.municipality_name:
                        lot.municipality_name = municipality
                        municipality_filled += 1
                    if settlement and not lot.settlement_name:
                        lot.settlement_name = settlement
                        settlement_filled += 1

                    total_processed += 1

                db.commit()
                last_id = lots[-1].id
        finally:
            db.close()

        total_settlement_filled = 0
        db_check = SessionLocal()
        try:
            total_settlement_filled = (
                db_check.query(Lot)
                .filter(Lot.settlement_name.isnot(None))
                .filter(Lot.settlement_name != "")
                .count()
            )
        finally:
            db_check.close()

        self.stdout.write(f"total_processed={total_processed}")
        self.stdout.write(f"settlement_filled_new={settlement_filled}")
        self.stdout.write(f"total_settlement_filled={total_settlement_filled}")
