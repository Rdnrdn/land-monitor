from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from land_monitor.db import SessionLocal
from land_monitor.models import Lot, Subject


CADASTRAL_NUMBER_CODES = {"CadastralNumber"}
AREA_CODES = {"SquareZU", "SquareZU_project"}
PERMITTED_USE_CODES = {"PermittedUse"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dict_value(value: Any, key: str) -> str | None:
    if not isinstance(value, dict):
        return None
    return _clean_text(value.get(key))


def _get_nested(mapping: dict[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _fias_guid(estate_address_fias: Any) -> str | None:
    return _clean_text(_get_nested(_as_dict(estate_address_fias), "addressByFIAS", "guid"))


def _characteristic_value(characteristics: Any, codes: set[str]) -> Any:
    if not isinstance(characteristics, list):
        return None
    for item in characteristics:
        if isinstance(item, dict) and item.get("code") in codes:
            return item.get("characteristicValue")
    return None


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


def _set_text_if_present(lot: Lot, field: str, value: Any, changed_fields: set[str]) -> bool:
    cleaned = _clean_text(value)
    if not cleaned:
        return False
    current = _clean_text(getattr(lot, field))
    if current == cleaned:
        return False
    setattr(lot, field, cleaned)
    changed_fields.add(field)
    return True


def _set_decimal_if_present(lot: Lot, field: str, value: Decimal | None, changed_fields: set[str]) -> bool:
    if value is None:
        return False
    current = getattr(lot, field)
    if current == value:
        return False
    setattr(lot, field, value)
    changed_fields.add(field)
    return True


class Command(BaseCommand):
    help = "Map normalized lot fields from already stored lots.raw_data['opendata']."

    def add_arguments(self, parser):
        parser.add_argument(
            "--report-path",
            default=None,
            help="Optional JSON report path. Defaults to .local/diagnostics/opendata_lot_field_mapping_<timestamp>.json.",
        )

    def handle(self, *args, **options):
        started_at = datetime.now(timezone.utc)
        db = SessionLocal()
        lots_seen = 0
        lots_with_opendata = 0
        changed_lots = 0
        unchanged_lots = 0
        field_updates: dict[str, int] = {}
        missing_subject_codes: dict[str, int] = {}
        examples: list[dict[str, Any]] = []

        try:
            subjects_by_code = {subject.code: subject for subject in db.query(Subject).all()}
            query = (
                db.query(Lot)
                .filter(Lot.raw_data["opendata"].isnot(None))
                .order_by(Lot.id)
            )

            for lot in query.yield_per(100):
                lots_seen += 1
                raw_data = _as_dict(lot.raw_data)
                opendata = _as_dict(raw_data.get("opendata"))
                if not opendata:
                    continue

                lots_with_opendata += 1
                changed_fields: set[str] = set()
                subject = _as_dict(opendata.get("subjectRF"))
                category = _as_dict(opendata.get("category"))
                ownership_form = _as_dict(opendata.get("ownershipForms"))
                characteristics = opendata.get("characteristics")

                subject_code = _dict_value(subject, "code")
                if subject_code:
                    _set_text_if_present(lot, "subject_rf_code", subject_code, changed_fields)
                    subject_row = subjects_by_code.get(subject_code)
                    if subject_row and lot.subject_id != subject_row.id:
                        lot.subject_id = subject_row.id
                        changed_fields.add("subject_id")
                    elif subject_row is None:
                        missing_subject_codes[subject_code] = missing_subject_codes.get(subject_code, 0) + 1

                _set_text_if_present(lot, "address", opendata.get("estateAddress"), changed_fields)
                _set_text_if_present(lot, "fias_guid", _fias_guid(opendata.get("estateAddressFIAS")), changed_fields)
                _set_text_if_present(lot, "category", _dict_value(category, "name"), changed_fields)
                _set_text_if_present(lot, "ownership_form_code", _dict_value(ownership_form, "code"), changed_fields)
                _set_text_if_present(lot, "ownership_form_name", _dict_value(ownership_form, "name"), changed_fields)
                _set_text_if_present(lot, "lot_status_external", opendata.get("lotStatus"), changed_fields)
                _set_text_if_present(lot, "description", opendata.get("lotDescription"), changed_fields)

                cadastral_number = _value_to_text(_characteristic_value(characteristics, CADASTRAL_NUMBER_CODES))
                area = _value_to_decimal(_characteristic_value(characteristics, AREA_CODES))
                permitted_use = _value_to_text(_characteristic_value(characteristics, PERMITTED_USE_CODES))

                _set_text_if_present(lot, "cadastre_number", cadastral_number, changed_fields)
                _set_decimal_if_present(lot, "area_m2", area, changed_fields)
                _set_text_if_present(lot, "permitted_use", permitted_use, changed_fields)

                if changed_fields:
                    lot.updated_at = started_at
                    changed_lots += 1
                    for field in changed_fields:
                        field_updates[field] = field_updates.get(field, 0) + 1
                else:
                    unchanged_lots += 1

                if len(examples) < 5:
                    examples.append(
                        {
                            "id": lot.id,
                            "source_lot_id": lot.source_lot_id,
                            "subject_rf_code": lot.subject_rf_code,
                            "subject_id": lot.subject_id,
                            "address": lot.address,
                            "fias_guid": lot.fias_guid,
                            "cadastre_number": lot.cadastre_number,
                            "area_m2": str(lot.area_m2) if lot.area_m2 is not None else None,
                            "permitted_use": lot.permitted_use,
                            "category": lot.category,
                            "ownership_form_code": lot.ownership_form_code,
                            "ownership_form_name": lot.ownership_form_name,
                        }
                    )

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        report_path = Path(
            options["report_path"]
            or f".local/diagnostics/opendata_lot_field_mapping_{started_at:%Y%m%d_%H%M%S}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "started_at": started_at.isoformat(),
            "lots_seen": lots_seen,
            "lots_with_opendata": lots_with_opendata,
            "changed_lots": changed_lots,
            "unchanged_lots": unchanged_lots,
            "field_updates": field_updates,
            "missing_subject_codes": missing_subject_codes,
            "examples": examples,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(f"lots_seen={lots_seen}")
        self.stdout.write(f"lots_with_opendata={lots_with_opendata}")
        self.stdout.write(f"changed_lots={changed_lots}")
        self.stdout.write(f"unchanged_lots={unchanged_lots}")
        self.stdout.write(f"field_updates={json.dumps(field_updates, ensure_ascii=False)}")
        self.stdout.write(f"missing_subject_codes={json.dumps(missing_subject_codes, ensure_ascii=False)}")
        self.stdout.write(f"examples={json.dumps(examples, ensure_ascii=False)}")
        self.stdout.write(f"report_path={report_path}")
