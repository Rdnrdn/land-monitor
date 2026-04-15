from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from land_monitor.db import SessionLocal
from land_monitor.models import Lot, Notice, Subject
from lots.opendata_fias import extract_fias_levels


SOURCE = "opendata_notice"
PUBLISHED_STATUS = "PUBLISHED"
CANCELED_STATUS = "CANCELED"
CADASTRAL_NUMBER_CODES = {"CadastralNumber"}
AREA_CODES = {"SquareZU", "SquareZU_project"}
PERMITTED_USE_CODES = {"PermittedUse"}
CONTRACT_TYPE_CODES = {"DA_contractType_IPS(ZK)", "DA_contractType_EA(ZK)"}
LAND_RESTRICTIONS_CODE = "DA_landRestrictions_EA(ZK)"
CONTRACT_SIGN_PERIOD_CODE = "DA_contractSignPeriod__EA(ZK)"
RENT_CONTRACT_CODES = {"leaseAgreement", "договор_аренды_земельного_участка_Select"}
SALE_CONTRACT_CODES = {"purchaseSaleAgreement", "договор_купли_продажи_земельного_участка_Select"}
UNKNOWN_CONTRACT_CODES = {"notEstablishedAgreement"}
APPLICATION_ADDRESS_DETAIL_CODES = (
    "DA_applicationAddressRules_IPS(ZK)",
    "DA_applicationAddressRules_EA(ZK)",
)
APPLICATION_ADDRESS_DETAIL_PREFIXES = ("DA_applicationAddressRules",)

LOT_SNAPSHOT_KEYS = (
    "lotNumber",
    "lotStatus",
    "lotName",
    "lotDescription",
    "deposit",
    "priceMin",
    "priceFin",
    "priceStep",
    "currency",
    "priceMinVAT",
    "biddingObjectInfo",
    "additionalDetails",
    "docs",
    "imageIds",
)
ALLOWED_FIAS_SCOPE_LEVELS = {3, 5, 6}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: str, option_name: str) -> date:
    cleaned = _clean_text(value)
    if not cleaned:
        raise CommandError(f"{option_name} must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise CommandError(f"{option_name} must use YYYY-MM-DD format.") from exc


def _get_nested(mapping: dict[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _dict_value(value: Any, key: str) -> str | None:
    if not isinstance(value, dict):
        return None
    return _clean_text(value.get(key))


def _value_to_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return _clean_text(value.get("name") or value.get("value") or value.get("code"))
    if isinstance(value, list):
        parts = [_value_to_text(item) for item in value]
        cleaned_parts = [part for part in parts if part]
        return ", ".join(cleaned_parts) if cleaned_parts else None
    return _clean_text(value)


def _value_to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    normalized = cleaned.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _characteristic_value(characteristics: Any, codes: set[str]) -> Any:
    if not isinstance(characteristics, list):
        return None
    for item in characteristics:
        if isinstance(item, dict) and item.get("code") in codes:
            return item.get("characteristicValue")
    return None


def _additional_details_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_contract_type_bucket(value_code: str | None, value_name: str | None) -> str | None:
    if value_code in RENT_CONTRACT_CODES:
        return "rent"
    if value_code in SALE_CONTRACT_CODES:
        return "sale"
    if value_code in UNKNOWN_CONTRACT_CODES:
        return "unknown"

    normalized_name = (value_name or "").strip().lower()
    if "аренд" in normalized_name:
        return "rent"
    if "купли-продажи" in normalized_name or "купля-продажа" in normalized_name:
        return "sale"
    if "не установлен" in normalized_name:
        return "unknown"
    return None


def _extract_lot_contract_terms(lot_snapshot: dict[str, Any]) -> dict[str, str | None]:
    contract_type_bucket: str | None = None
    contract_type_source_code: str | None = None
    contract_type_source_name: str | None = None
    land_restrictions_text: str | None = None
    contract_sign_period_text: str | None = None

    for detail in _additional_details_items(lot_snapshot.get("additionalDetails")):
        detail_code = _clean_text(detail.get("code"))
        value = detail.get("value")
        value_code = _dict_value(value, "code")
        value_name = _dict_value(value, "name") or _clean_text(value)

        if detail_code in CONTRACT_TYPE_CODES and contract_type_bucket is None:
            contract_type_bucket = _normalize_contract_type_bucket(value_code, value_name)
            contract_type_source_code = value_code
            contract_type_source_name = value_name
            continue

        if detail_code == LAND_RESTRICTIONS_CODE and land_restrictions_text is None:
            land_restrictions_text = value_name
            continue

        if detail_code == CONTRACT_SIGN_PERIOD_CODE and contract_sign_period_text is None:
            contract_sign_period_text = value_name

    return {
        "contract_type_bucket": contract_type_bucket,
        "contract_type_source_code": contract_type_source_code,
        "contract_type_source_name": contract_type_source_name,
        "land_restrictions_text": land_restrictions_text,
        "contract_sign_period_text": contract_sign_period_text,
    }


def _fias_guid(estate_address_fias: Any) -> str | None:
    return _clean_text(_get_nested(_as_dict(estate_address_fias), "addressByFIAS", "guid"))


def _parse_fias_scope(value: str) -> dict[str, Any]:
    cleaned = _clean_text(value)
    if not cleaned:
        raise CommandError("--fias-scope must use SUBJECT_RF_CODE:LEVEL:GUID format.")
    parts = [part.strip() for part in cleaned.split(":", 2)]
    if len(parts) != 3 or not all(parts):
        raise CommandError("--fias-scope must use SUBJECT_RF_CODE:LEVEL:GUID format.")
    subject_rf_code, level_raw, guid = parts
    try:
        level = int(level_raw)
    except ValueError as exc:
        raise CommandError("--fias-scope level must be an integer.") from exc
    if level not in ALLOWED_FIAS_SCOPE_LEVELS:
        raise CommandError("--fias-scope level must be one of 3, 5, 6.")
    return {
        "subject_rf_code": subject_rf_code,
        "level": level,
        "guid": guid,
        "label": f"{subject_rf_code}:level_{level}:{guid}",
    }


def _opendata_notice_payload(raw_data: Any) -> dict[str, Any]:
    raw = _as_dict(raw_data)
    opendata = _as_dict(raw.get("opendata"))
    return _as_dict(_get_nested(opendata, "exportObject", "structuredObject", "notice"))


def _notice_number(notice_row: Notice, notice_payload: dict[str, Any]) -> str | None:
    return _clean_text(notice_row.notice_number) or _clean_text(
        _get_nested(notice_payload, "commonInfo", "noticeNumber")
    )


def _notice_source_meta(raw_data: Any) -> dict[str, Any]:
    return _as_dict(_as_dict(raw_data).get("opendata_meta"))


def _notice_source_url(notice_payload: dict[str, Any], source_meta: dict[str, Any]) -> str:
    return (
        _clean_text(_get_nested(notice_payload, "commonInfo", "href"))
        or _clean_text(source_meta.get("href"))
        or _clean_text(source_meta.get("source"))
        or ""
    )


def _notice_subset(
    notice_payload: dict[str, Any],
    source_meta: dict[str, Any],
) -> dict[str, Any]:
    common_info = _as_dict(notice_payload.get("commonInfo"))
    return {
        "noticeNumber": common_info.get("noticeNumber") or source_meta.get("regNum"),
        "publishDate": common_info.get("publishDate") or source_meta.get("publishDate"),
        "publicNoticeUrl": common_info.get("href"),
        "biddType": common_info.get("biddType"),
        "biddConditions": notice_payload.get("biddConditions"),
        "bidderOrg": notice_payload.get("bidderOrg"),
        "rightHolderInfo": notice_payload.get("rightHolderInfo"),
        "opendata_meta": source_meta,
    }


def _notice_bidd_type_code(notice_payload: dict[str, Any]) -> str | None:
    common_info = _as_dict(notice_payload.get("commonInfo"))
    return _dict_value(common_info.get("biddType"), "code")


def _notice_additional_details(notice_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _additional_details_items(notice_payload.get("additionalDetails"))


def _notice_application_address(notice_payload: dict[str, Any]) -> str | None:
    details = _notice_additional_details(notice_payload)
    for code in APPLICATION_ADDRESS_DETAIL_CODES:
        for item in details:
            if item.get("code") != code:
                continue
            value = _value_to_text(item.get("value"))
            if value:
                return value

    for item in details:
        detail_code = _clean_text(item.get("code")) or ""
        if not any(detail_code.startswith(prefix) for prefix in APPLICATION_ADDRESS_DETAIL_PREFIXES):
            continue
        value = _value_to_text(item.get("value"))
        if value:
            return value
    return None


def _notice_url(notice_number: str | None) -> str | None:
    if not notice_number:
        return None
    return f"https://torgi.gov.ru/new/public/notices/view/{notice_number}"


def _notice_summary_values(
    notice_row: Notice,
    notice_payload: dict[str, Any],
) -> dict[str, Any]:
    notice_number = _notice_number(notice_row, notice_payload)
    bidd_conditions = _as_dict(notice_payload.get("biddConditions"))
    application_start_at = _parse_timestamp(bidd_conditions.get("biddStartTime"))
    application_deadline = _parse_timestamp(bidd_conditions.get("biddEndTime"))
    return {
        "notice_number": notice_number,
        "notice_publish_date": notice_row.publish_date,
        "application_start_date": application_start_at,
        "application_start_at": application_start_at,
        "application_deadline": application_deadline,
        "application_address": _notice_application_address(notice_payload),
        "notice_url": _notice_url(notice_number),
    }


def _lot_snapshot(lot_payload: dict[str, Any]) -> dict[str, Any]:
    bidding_object = _as_dict(lot_payload.get("biddingObjectInfo"))
    snapshot = {
        key: lot_payload.get(key)
        for key in LOT_SNAPSHOT_KEYS
        if lot_payload.get(key) is not None
    }
    extracted = {
        "estateAddress": lot_payload.get("estateAddress") or bidding_object.get("estateAddress"),
        "estateAddressFIAS": lot_payload.get("estateAddressFIAS") or bidding_object.get("estateAddressFIAS"),
        "subjectRF": lot_payload.get("subjectRF") or bidding_object.get("subjectRF"),
        "category": lot_payload.get("category") or bidding_object.get("category"),
        "ownershipForms": lot_payload.get("ownershipForms") or bidding_object.get("ownershipForms"),
        "characteristics": lot_payload.get("characteristics") or bidding_object.get("characteristics"),
    }
    snapshot.update({key: value for key, value in extracted.items() if value is not None})
    return snapshot


def _lot_scope_match(
    lot_snapshot: dict[str, Any],
    fias_scopes: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, str | None], str | None]:
    subject_code = _dict_value(_as_dict(lot_snapshot.get("subjectRF")), "code")
    fias_levels = extract_fias_levels(lot_snapshot.get("estateAddressFIAS"))
    if not fias_scopes:
        return None, fias_levels, subject_code

    for scope in fias_scopes:
        if subject_code != scope["subject_rf_code"]:
            continue
        level_guid = fias_levels.get(f"fias_level_{scope['level']}_guid")
        if level_guid and level_guid == scope["guid"]:
            return scope, fias_levels, subject_code
    return None, fias_levels, subject_code


def _merge_raw_data(
    existing: Any,
    *,
    lot_snapshot: dict[str, Any],
    notice_subset: dict[str, Any],
) -> dict[str, Any]:
    raw_data = dict(existing) if isinstance(existing, dict) else {}
    raw_data["opendata"] = lot_snapshot
    raw_data["opendata_notice"] = notice_subset
    return raw_data


def _set_text_if_present(lot: Lot, field: str, value: Any, changed_fields: set[str]) -> None:
    cleaned = _clean_text(value)
    if not cleaned:
        return
    current = _clean_text(getattr(lot, field))
    if current == cleaned:
        return
    setattr(lot, field, cleaned)
    changed_fields.add(field)


def _set_decimal_if_present(lot: Lot, field: str, value: Decimal | None, changed_fields: set[str]) -> None:
    if value is None:
        return
    current = getattr(lot, field)
    if current == value:
        return
    setattr(lot, field, value)
    changed_fields.add(field)


def _subject_id(subjects_by_code: dict[str, Subject], subject_code: str | None) -> int | None:
    if not subject_code:
        return None
    subject = subjects_by_code.get(subject_code)
    return subject.id if subject else None


def _mapped_values(
    lot_snapshot: dict[str, Any],
    *,
    subjects_by_code: dict[str, Subject],
    source_notice_bidd_type_code: str | None,
    notice_summary: dict[str, Any] | None = None,
    fias_levels: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    subject = _as_dict(lot_snapshot.get("subjectRF"))
    category = _as_dict(lot_snapshot.get("category"))
    ownership_form = _as_dict(lot_snapshot.get("ownershipForms"))
    characteristics = lot_snapshot.get("characteristics")
    subject_code = _dict_value(subject, "code")
    fias_levels = fias_levels or extract_fias_levels(lot_snapshot.get("estateAddressFIAS"))
    contract_terms = _extract_lot_contract_terms(lot_snapshot)
    notice_summary = notice_summary or {}

    return {
        "notice_number": notice_summary.get("notice_number"),
        "notice_publish_date": notice_summary.get("notice_publish_date"),
        "application_start_date": notice_summary.get("application_start_date"),
        "application_start_at": notice_summary.get("application_start_at"),
        "application_deadline": notice_summary.get("application_deadline"),
        "application_address": notice_summary.get("application_address"),
        "notice_url": notice_summary.get("notice_url"),
        "title": _clean_text(lot_snapshot.get("lotName")),
        "description": _clean_text(lot_snapshot.get("lotDescription")),
        "subject_rf_code": subject_code,
        "subject_id": _subject_id(subjects_by_code, subject_code),
        "address": _clean_text(lot_snapshot.get("estateAddress")),
        "fias_guid": _fias_guid(lot_snapshot.get("estateAddressFIAS")),
        "category": _dict_value(category, "name"),
        "ownership_form_code": _dict_value(ownership_form, "code"),
        "ownership_form_name": _dict_value(ownership_form, "name"),
        "lot_status_external": _clean_text(lot_snapshot.get("lotStatus")),
        "source_notice_bidd_type_code": source_notice_bidd_type_code,
        "price_min": _value_to_decimal(lot_snapshot.get("priceMin")),
        "price_fin": _value_to_decimal(lot_snapshot.get("priceFin")),
        "deposit_amount": _value_to_decimal(lot_snapshot.get("deposit")),
        "currency_code": _dict_value(lot_snapshot.get("currency"), "code"),
        "cadastre_number": _value_to_text(_characteristic_value(characteristics, CADASTRAL_NUMBER_CODES)),
        "area_m2": _value_to_decimal(_characteristic_value(characteristics, AREA_CODES)),
        "permitted_use": _value_to_text(_characteristic_value(characteristics, PERMITTED_USE_CODES)),
        **contract_terms,
        **fias_levels,
    }


def _apply_mapped_values(lot: Lot, mapped_values: dict[str, Any]) -> set[str]:
    changed_fields: set[str] = set()
    for field in (
        "notice_number",
        "notice_url",
        "title",
        "description",
        "subject_rf_code",
        "address",
        "fias_guid",
        "category",
        "ownership_form_code",
        "ownership_form_name",
        "lot_status_external",
        "source_notice_bidd_type_code",
        "currency_code",
        "contract_type_bucket",
        "contract_type_source_code",
        "contract_type_source_name",
        "land_restrictions_text",
        "contract_sign_period_text",
        "fias_level_3_guid",
        "fias_level_3_name",
        "fias_level_5_guid",
        "fias_level_5_name",
        "fias_level_6_guid",
        "fias_level_6_name",
        "cadastre_number",
        "permitted_use",
        "application_address",
    ):
        _set_text_if_present(lot, field, mapped_values.get(field), changed_fields)

    _set_decimal_if_present(lot, "price_min", mapped_values.get("price_min"), changed_fields)
    _set_decimal_if_present(lot, "price_fin", mapped_values.get("price_fin"), changed_fields)
    _set_decimal_if_present(lot, "deposit_amount", mapped_values.get("deposit_amount"), changed_fields)
    _set_decimal_if_present(lot, "area_m2", mapped_values.get("area_m2"), changed_fields)

    for field in (
        "notice_publish_date",
        "application_start_date",
        "application_start_at",
        "application_deadline",
    ):
        value = mapped_values.get(field)
        if value is None or getattr(lot, field) == value:
            continue
        setattr(lot, field, value)
        changed_fields.add(field)

    subject_id = mapped_values.get("subject_id")
    if subject_id is not None and lot.subject_id != subject_id:
        lot.subject_id = subject_id
        changed_fields.add("subject_id")

    return changed_fields


def _new_lot(
    *,
    source_lot_id: str,
    source_url: str,
    notice_number: str,
    raw_data: dict[str, Any],
    mapped_values: dict[str, Any],
) -> Lot:
    return Lot(
        source=SOURCE,
        source_lot_id=source_lot_id,
        source_url=source_url,
        notice_number=notice_number,
        notice_publish_date=mapped_values.get("notice_publish_date"),
        notice_url=mapped_values.get("notice_url"),
        title=mapped_values.get("title"),
        description=mapped_values.get("description"),
        subject_id=mapped_values.get("subject_id"),
        subject_rf_code=mapped_values.get("subject_rf_code"),
        address=mapped_values.get("address"),
        fias_guid=mapped_values.get("fias_guid"),
        cadastre_number=mapped_values.get("cadastre_number"),
        area_m2=mapped_values.get("area_m2"),
        category=mapped_values.get("category"),
        permitted_use=mapped_values.get("permitted_use"),
        ownership_form_code=mapped_values.get("ownership_form_code"),
        ownership_form_name=mapped_values.get("ownership_form_name"),
        price_min=mapped_values.get("price_min"),
        price_fin=mapped_values.get("price_fin"),
        deposit_amount=mapped_values.get("deposit_amount"),
        currency_code=mapped_values.get("currency_code"),
        lot_status_external=mapped_values.get("lot_status_external"),
        source_notice_bidd_type_code=mapped_values.get("source_notice_bidd_type_code"),
        contract_type_bucket=mapped_values.get("contract_type_bucket"),
        contract_type_source_code=mapped_values.get("contract_type_source_code"),
        contract_type_source_name=mapped_values.get("contract_type_source_name"),
        land_restrictions_text=mapped_values.get("land_restrictions_text"),
        contract_sign_period_text=mapped_values.get("contract_sign_period_text"),
        application_start_date=mapped_values.get("application_start_date"),
        application_start_at=mapped_values.get("application_start_at"),
        application_deadline=mapped_values.get("application_deadline"),
        application_address=mapped_values.get("application_address"),
        fias_level_3_guid=mapped_values.get("fias_level_3_guid"),
        fias_level_3_name=mapped_values.get("fias_level_3_name"),
        fias_level_5_guid=mapped_values.get("fias_level_5_guid"),
        fias_level_5_name=mapped_values.get("fias_level_5_name"),
        fias_level_6_guid=mapped_values.get("fias_level_6_guid"),
        fias_level_6_name=mapped_values.get("fias_level_6_name"),
        raw_data=raw_data,
    )


def _percent(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count * 100 / total, 2)


class Command(BaseCommand):
    help = "Controlled sync lots from already stored notices.raw_data['opendata'] notice.lots[]."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not write to the database. A diagnostic report is still written.",
        )
        parser.add_argument(
            "--limit-notices",
            type=int,
            required=True,
            help="Safety cap for notices processed. Required to avoid accidental mass backfill.",
        )
        parser.add_argument(
            "--after-notice-number",
            default=None,
            help="Optional exclusive cursor. Only notices with notice_number greater than this value are considered.",
        )
        parser.add_argument(
            "--report-path",
            default=None,
            help="Optional JSON report path. Defaults to .local/diagnostics/opendata_notice_lot_sync_<timestamp>.json.",
        )
        parser.add_argument(
            "--publish-date-from",
            default=None,
            help="Optional inclusive publish_date lower bound for candidate notices, YYYY-MM-DD.",
        )
        parser.add_argument(
            "--fias-scope",
            action="append",
            default=[],
            metavar="SUBJECT:LEVEL:GUID",
            help="Optional repeatable lot-level scope in SUBJECT_RF_CODE:LEVEL:GUID format. Level must be 3, 5, or 6.",
        )

    def handle(self, *args, **options):
        started_at = datetime.now(timezone.utc)
        dry_run = bool(options["dry_run"])
        limit_notices = int(options["limit_notices"])
        after_notice_number = _clean_text(options.get("after_notice_number"))
        publish_date_from_raw = _clean_text(options.get("publish_date_from"))
        publish_date_from = (
            _parse_date(publish_date_from_raw, "--publish-date-from")
            if publish_date_from_raw
            else None
        )
        publish_date_from_dt = (
            datetime.combine(publish_date_from, time.min, tzinfo=timezone.utc)
            if publish_date_from
            else None
        )
        fias_scopes = [_parse_fias_scope(value) for value in options.get("fias_scope") or []]
        if limit_notices <= 0:
            raise CommandError("--limit-notices must be a positive integer.")

        stats: dict[str, Any] = {
            "notices_scanned": 0,
            "notices_processed": 0,
            "lots_processed": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "matched_existing": 0,
            "newly_created": 0,
            "skipped_non_zk_notices": 0,
            "skipped_non_zk_lots": 0,
            "skipped_non_published": 0,
            "skipped_malformed": 0,
            "errors": 0,
            "coverage_total": 0,
            "coverage_subject": 0,
            "coverage_address": 0,
            "coverage_area": 0,
            "coverage_cadastre": 0,
            "field_updates": {},
            "examples": [],
            "problem_examples": [],
            "after_notice_number": after_notice_number,
            "publish_date_from": publish_date_from.isoformat() if publish_date_from else None,
            "fias_scopes": fias_scopes,
            "first_notice_number_in_batch": None,
            "last_notice_number_in_batch": None,
            "notices_skipped_by_publish_date": 0,
            "notices_skipped_by_fias_scope": 0,
            "lot_objects_scanned": 0,
            "scoped_lot_candidates": 0,
            "scope_hit_counts": {},
        }

        db = SessionLocal()
        try:
            subjects_by_code = {subject.code: subject for subject in db.query(Subject).all()}
            query = db.query(Notice).filter(Notice.raw_data["opendata"].isnot(None))
            if after_notice_number:
                query = query.filter(Notice.notice_number > after_notice_number)
            if publish_date_from_dt is not None:
                query = query.filter(Notice.publish_date.isnot(None), Notice.publish_date >= publish_date_from_dt)
            query = query.order_by(Notice.notice_number).limit(limit_notices)

            for notice_row in query.yield_per(25):
                if stats["first_notice_number_in_batch"] is None:
                    stats["first_notice_number_in_batch"] = notice_row.notice_number
                stats["last_notice_number_in_batch"] = notice_row.notice_number
                stats["notices_scanned"] += 1
                raw_data = _as_dict(notice_row.raw_data)
                notice_payload = _opendata_notice_payload(raw_data)
                lots_payload = notice_payload.get("lots")
                if not isinstance(lots_payload, list) or not lots_payload:
                    continue

                source_meta = _notice_source_meta(raw_data)
                notice_number = _notice_number(notice_row, notice_payload)
                notice_bidd_type_code = _notice_bidd_type_code(notice_payload)
                if notice_bidd_type_code != "ZK":
                    stats["skipped_non_zk_notices"] += 1
                    stats["skipped_non_zk_lots"] += len(lots_payload)
                    if len(stats["problem_examples"]) < 20:
                        stats["problem_examples"].append(
                            {
                                "notice_number": notice_number,
                                "reason": "non_zk_notice_skipped",
                                "biddTypeCode": notice_bidd_type_code,
                                "lots_count": len(lots_payload),
                            }
                        )
                    continue

                stats["notices_processed"] += 1
                notice_subset = _notice_subset(notice_payload, source_meta)
                notice_summary = _notice_summary_values(notice_row, notice_payload)
                source_url = _notice_source_url(notice_payload, source_meta)
                notice_has_scope_match = False

                for lot_payload in lots_payload:
                    stats["lot_objects_scanned"] += 1
                    try:
                        if not isinstance(lot_payload, dict):
                            stats["skipped"] += 1
                            stats["skipped_malformed"] += 1
                            continue

                        lot_number = _clean_text(lot_payload.get("lotNumber"))
                        if not notice_number or not lot_number:
                            stats["skipped"] += 1
                            stats["skipped_malformed"] += 1
                            if len(stats["problem_examples"]) < 20:
                                stats["problem_examples"].append(
                                    {
                                        "notice_number": notice_number,
                                        "lotNumber": lot_number,
                                        "reason": "missing_notice_number_or_lotNumber",
                                    }
                                )
                            continue

                        source_lot_id = f"{notice_number}_{lot_number}"
                        lot_snapshot = _lot_snapshot(lot_payload)
                        matched_scope, fias_levels, matched_subject_code = _lot_scope_match(
                            lot_snapshot,
                            fias_scopes,
                        )
                        if fias_scopes and matched_scope is None:
                            stats["skipped"] += 1
                            continue

                        notice_has_scope_match = True
                        stats["lots_processed"] += 1
                        stats["scoped_lot_candidates"] += 1
                        if matched_scope is not None:
                            label = matched_scope["label"]
                            stats["scope_hit_counts"][label] = stats["scope_hit_counts"].get(label, 0) + 1
                        mapped_values = _mapped_values(
                            lot_snapshot,
                            subjects_by_code=subjects_by_code,
                            source_notice_bidd_type_code=notice_bidd_type_code,
                            notice_summary=notice_summary,
                            fias_levels=fias_levels,
                        )
                        lot_status = _clean_text(lot_snapshot.get("lotStatus"))
                        raw_snapshot = _merge_raw_data(
                            {},
                            lot_snapshot=lot_snapshot,
                            notice_subset=notice_subset,
                        )

                        stats["coverage_total"] += 1
                        if mapped_values.get("subject_rf_code") or matched_subject_code:
                            stats["coverage_subject"] += 1
                        if mapped_values.get("address"):
                            stats["coverage_address"] += 1
                        if mapped_values.get("area_m2") is not None:
                            stats["coverage_area"] += 1
                        if mapped_values.get("cadastre_number"):
                            stats["coverage_cadastre"] += 1

                        lot = (
                            db.query(Lot)
                            .filter(Lot.source == SOURCE, Lot.source_lot_id == source_lot_id)
                            .one_or_none()
                        )
                        if lot is None and lot_status != PUBLISHED_STATUS:
                            stats["skipped"] += 1
                            stats["skipped_non_published"] += 1
                            continue

                        if lot is None:
                            lot = _new_lot(
                                source_lot_id=source_lot_id,
                                source_url=source_url,
                                notice_number=notice_number,
                                raw_data=raw_snapshot,
                                mapped_values=mapped_values,
                            )
                            db.add(lot)
                            stats["created"] += 1
                            stats["newly_created"] += 1
                            if len(stats["examples"]) < 10:
                                stats["examples"].append(
                                    {
                                        "action": "create",
                                        "notice_number": notice_number,
                                        "lotNumber": lot_number,
                                        "source_lot_id": source_lot_id,
                                        "lotStatus": lot_status,
                                        "scope": matched_scope["label"] if matched_scope else None,
                                    }
                                )
                            continue

                        stats["matched_existing"] += 1
                        changed_fields = _apply_mapped_values(lot, mapped_values)

                        merged_raw_data = _merge_raw_data(
                            lot.raw_data,
                            lot_snapshot=lot_snapshot,
                            notice_subset=notice_subset,
                        )
                        if merged_raw_data != lot.raw_data:
                            lot.raw_data = merged_raw_data
                            changed_fields.add("raw_data")
                        if source_url and lot.source_url != source_url:
                            lot.source_url = source_url
                            changed_fields.add("source_url")

                        if changed_fields:
                            lot.updated_at = started_at
                            stats["updated"] += 1
                            for field in changed_fields:
                                stats["field_updates"][field] = stats["field_updates"].get(field, 0) + 1
                            if len(stats["examples"]) < 10:
                                stats["examples"].append(
                                    {
                                        "action": "update",
                                        "notice_number": notice_number,
                                        "lotNumber": lot_number,
                                        "source_lot_id": source_lot_id,
                                        "lotStatus": lot_status,
                                        "changed_fields": sorted(changed_fields),
                                        "scope": matched_scope["label"] if matched_scope else None,
                                    }
                                )
                    except Exception as exc:  # noqa: BLE001 - per-lot diagnostics must not stop the batch.
                        stats["errors"] += 1
                        stats["skipped"] += 1
                        if len(stats["problem_examples"]) < 20:
                            stats["problem_examples"].append(
                                {
                                    "notice_number": notice_number,
                                    "lotNumber": lot_payload.get("lotNumber") if isinstance(lot_payload, dict) else None,
                                    "reason": type(exc).__name__,
                                    "error": str(exc),
                                }
                            )

                if fias_scopes and not notice_has_scope_match:
                    stats["notices_skipped_by_fias_scope"] += 1

            if dry_run:
                db.rollback()
            else:
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        coverage_denominator = int(stats["coverage_total"])
        stats["coverage"] = {
            "subject": {
                "count": stats["coverage_subject"],
                "total": coverage_denominator,
                "percent": _percent(stats["coverage_subject"], coverage_denominator),
            },
            "address": {
                "count": stats["coverage_address"],
                "total": coverage_denominator,
                "percent": _percent(stats["coverage_address"], coverage_denominator),
            },
            "area": {
                "count": stats["coverage_area"],
                "total": coverage_denominator,
                "percent": _percent(stats["coverage_area"], coverage_denominator),
            },
            "cadastre": {
                "count": stats["coverage_cadastre"],
                "total": coverage_denominator,
                "percent": _percent(stats["coverage_cadastre"], coverage_denominator),
            },
        }
        stats["started_at"] = started_at.isoformat()
        stats["dry_run"] = dry_run
        stats["limit_notices"] = limit_notices

        report_path = Path(
            options["report_path"]
            or f".local/diagnostics/opendata_notice_lot_sync_{started_at:%Y%m%d_%H%M%S}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

        for key in (
            "notices_scanned",
            "notices_processed",
            "notices_skipped_by_publish_date",
            "notices_skipped_by_fias_scope",
            "lot_objects_scanned",
            "lots_processed",
            "scoped_lot_candidates",
            "created",
            "updated",
            "skipped",
            "matched_existing",
            "newly_created",
            "skipped_non_zk_notices",
            "skipped_non_zk_lots",
            "skipped_non_published",
            "skipped_malformed",
            "errors",
        ):
            self.stdout.write(f"{key}={stats[key]}")
        self.stdout.write(f"coverage_subject={json.dumps(stats['coverage']['subject'], ensure_ascii=False)}")
        self.stdout.write(f"coverage_address={json.dumps(stats['coverage']['address'], ensure_ascii=False)}")
        self.stdout.write(f"coverage_area={json.dumps(stats['coverage']['area'], ensure_ascii=False)}")
        self.stdout.write(f"coverage_cadastre={json.dumps(stats['coverage']['cadastre'], ensure_ascii=False)}")
        self.stdout.write(f"scope_hit_counts={json.dumps(stats['scope_hit_counts'], ensure_ascii=False)}")
        self.stdout.write(f"field_updates={json.dumps(stats['field_updates'], ensure_ascii=False)}")
        self.stdout.write(f"examples={json.dumps(stats['examples'], ensure_ascii=False)}")
        self.stdout.write(f"problem_examples={json.dumps(stats['problem_examples'][:5], ensure_ascii=False)}")
        self.stdout.write(f"after_notice_number={stats['after_notice_number']}")
        self.stdout.write(f"first_notice_number_in_batch={stats['first_notice_number_in_batch']}")
        self.stdout.write(f"last_notice_number_in_batch={stats['last_notice_number_in_batch']}")
        self.stdout.write(f"dry_run={dry_run}")
        self.stdout.write(f"report_path={report_path}")
