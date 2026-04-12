from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError

from land_monitor.db import SessionLocal
from land_monitor.models import Notice, OpendataNoticeVersion


LIST_URL = "https://torgi.gov.ru/new/opendata/list.json"
NOTICE_IDENTIFIER = "7710568760-notice"
DEFAULT_SUBJECT_CODES = ("77", "50", "40", "71")
HEADERS = {
    "User-Agent": "land-monitor-opendata-notice-ingest/0.1",
    "Accept": "application/json, text/plain, */*",
}
DATA_SOURCE_PERIOD_RE = re.compile(r"data-(\d{8})T\d{4}-(\d{8})T\d{4}-")


def _parse_date(value: str, option_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"{option_name} must use YYYY-MM-DD format.") from exc


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _period_from_source(source: str) -> tuple[date, date] | None:
    match = DATA_SOURCE_PERIOD_RE.search(source)
    if not match:
        return None
    return (
        datetime.strptime(match.group(1), "%Y%m%d").date(),
        datetime.strptime(match.group(2), "%Y%m%d").date(),
    )


def _period_kind(start_date: date, end_exclusive: date) -> str:
    days = (end_exclusive - start_date).days
    if days == 1:
        return "daily"
    if 28 <= days <= 31 and start_date.day == 1 and end_exclusive.day == 1:
        return "monthly"
    return "range"


def _period_overlaps(
    file_start: date,
    file_end_exclusive: date,
    query_start: date,
    query_end_inclusive: date,
) -> bool:
    query_end_exclusive = query_end_inclusive + timedelta(days=1)
    return file_start < query_end_exclusive and query_start < file_end_exclusive


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get_nested(mapping: dict[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _nested_name(value: Any) -> str | None:
    if isinstance(value, dict):
        name = value.get("name")
        return str(name).strip() if name else None
    return None


def _fetch_json(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    retries: int,
    retry_delay: float,
) -> tuple[dict[str, Any] | list[Any] | None, str]:
    last_status = "error"
    for attempt in range(retries + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
            if response.status_code == 503:
                last_status = "http_503"
                if attempt < retries:
                    time.sleep(retry_delay)
                    continue
                return None, "http_503"
            response.raise_for_status()
            return response.json(), "ok"
        except requests.exceptions.Timeout:
            last_status = "timeout"
        except requests.RequestException as exc:
            last_status = f"http_error:{type(exc).__name__}"
        except ValueError:
            return None, "invalid_json"

        if attempt < retries:
            time.sleep(retry_delay)
    return None, last_status


def _notice_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    notice = _get_nested(payload, "exportObject", "structuredObject", "notice")
    return notice if isinstance(notice, dict) else {}


def _notice_number(item: dict[str, Any], notice: dict[str, Any]) -> str | None:
    value = item.get("regNum") or _get_nested(notice, "commonInfo", "noticeNumber") or notice.get("noticeNumber")
    return str(value).strip() if value else None


def _notice_values(
    *,
    item: dict[str, Any],
    payload: dict[str, Any],
    fetched_at: datetime,
    source_date: str,
) -> dict[str, Any] | None:
    notice = _notice_from_payload(payload)
    notice_number = _notice_number(item, notice)
    if not notice_number:
        return None

    common = _as_dict(notice.get("commonInfo"))
    bidder_org = _as_dict(notice.get("bidderOrg"))
    bidder_org_info = _as_dict(bidder_org.get("orgInfo"))
    right_holder_info = _as_dict(notice.get("rightHolderInfo"))
    right_holder_org = _as_dict(right_holder_info.get("rightHolderOrgInfo"))

    bidd_type = common.get("biddType") or notice.get("biddType")
    bidd_form = common.get("biddForm") or notice.get("biddForm")
    publish_date = _parse_dt(common.get("publishDate") or notice.get("publishDate") or item.get("publishDate"))
    create_date = _parse_dt(common.get("createDate") or notice.get("createDate"))
    update_date = _parse_dt(common.get("updateDate") or notice.get("updateDate"))

    return {
        "notice_number": notice_number,
        "notice_status": common.get("noticeStatus") or notice.get("noticeStatus"),
        "publish_date": publish_date,
        "create_date": create_date,
        "update_date": update_date,
        "bidd_type_code": _get_nested(bidd_type, "code"),
        "bidd_form_code": _get_nested(bidd_form, "code"),
        "bidder_org_name": bidder_org_info.get("name") or bidder_org.get("name"),
        "right_holder_name": right_holder_org.get("name") or right_holder_info.get("name"),
        "fetched_at": fetched_at,
        "opendata_meta": {
            "source": "torgi_opendata",
            "source_date": source_date,
            "href": item.get("href"),
            "documentType": item.get("documentType"),
            "regNum": item.get("regNum"),
            "subjectEstateCode": item.get("subjectEstateCode"),
            "publishDate": item.get("publishDate"),
            "ingested_at": fetched_at.isoformat(),
        },
        "opendata_payload": payload,
    }


def _merge_raw_data(existing: Any, opendata_payload: dict[str, Any], opendata_meta: dict[str, Any]) -> dict[str, Any]:
    raw_data = dict(existing) if isinstance(existing, dict) else {}
    raw_data["opendata"] = opendata_payload
    raw_data["opendata_meta"] = opendata_meta
    return raw_data


def _meta_without_ingested_at(value: Any) -> dict[str, Any]:
    meta = dict(value) if isinstance(value, dict) else {}
    meta.pop("ingested_at", None)
    return meta


def _version_key_values(item: dict[str, Any]) -> dict[str, Any] | None:
    reg_num = str(item.get("regNum") or "").strip()
    document_type = str(item.get("documentType") or "").strip()
    publish_date = _parse_dt(item.get("publishDate"))
    source_date_raw = str(item.get("source_date") or "").strip()
    href = str(item.get("href") or "").strip()
    if not reg_num or not document_type or publish_date is None or not source_date_raw or not href:
        return None
    try:
        source_date = date.fromisoformat(source_date_raw)
    except ValueError:
        return None
    return {
        "reg_num": reg_num,
        "document_type": document_type,
        "publish_date": publish_date,
        "source_date": source_date,
        "href": href,
    }


def _version_identity(key_values: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(key_values["reg_num"]),
        str(key_values["document_type"]),
        key_values["publish_date"].isoformat(),
        str(key_values["href"]),
    )


def _candidate_key_pairs(
    candidates: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in candidates:
        key_values = _version_key_values(item)
        if key_values is None:
            errors.append(
                {
                    "stage": "ledger_key",
                    "href": item.get("href"),
                    "regNum": item.get("regNum"),
                    "status": "invalid_version_key",
                }
            )
            continue
        pairs.append((item, key_values))
    return pairs


def _processed_version_identities(
    db,
    key_values_list: list[dict[str, Any]],
) -> set[tuple[str, str, str, str]]:
    reg_nums = sorted({str(key_values["reg_num"]) for key_values in key_values_list})
    if not reg_nums:
        return set()

    processed: set[tuple[str, str, str, str]] = set()
    chunk_size = 1000
    for offset in range(0, len(reg_nums), chunk_size):
        chunk = reg_nums[offset : offset + chunk_size]
        rows = (
            db.query(OpendataNoticeVersion)
            .filter(
                OpendataNoticeVersion.reg_num.in_(chunk),
                OpendataNoticeVersion.status == "processed",
            )
            .all()
        )
        for row in rows:
            processed.add(
                (
                    str(row.reg_num),
                    str(row.document_type),
                    row.publish_date.isoformat(),
                    str(row.href),
                )
            )
    return processed


def _filter_backlog_pairs(
    candidate_pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    processed_identities: set[tuple[str, str, str, str]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (item, key_values)
        for item, key_values in candidate_pairs
        if _version_identity(key_values) not in processed_identities
    ]


def _effective_backlog_pairs(
    db,
    candidates: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], int, int, int]:
    candidate_pairs = _candidate_key_pairs(candidates, errors)
    processed_identities = _processed_version_identities(
        db,
        [key_values for _, key_values in candidate_pairs],
    )
    backlog_pairs = _filter_backlog_pairs(candidate_pairs, processed_identities)
    hrefs_already_processed = len(candidate_pairs) - len(backlog_pairs)
    invalid_version_keys = len(candidates) - len(candidate_pairs)
    return backlog_pairs, len(candidate_pairs), hrefs_already_processed, invalid_version_keys


def _get_or_create_ledger_entry(db, key_values: dict[str, Any], now: datetime) -> tuple[OpendataNoticeVersion, bool]:
    version = (
        db.query(OpendataNoticeVersion)
        .filter(
            OpendataNoticeVersion.reg_num == key_values["reg_num"],
            OpendataNoticeVersion.document_type == key_values["document_type"],
            OpendataNoticeVersion.publish_date == key_values["publish_date"],
            OpendataNoticeVersion.href == key_values["href"],
        )
        .one_or_none()
    )
    if version is not None:
        return version, False

    version = OpendataNoticeVersion(
        **key_values,
        status="downloaded",
        downloaded_at=now,
        updated_at=now,
    )
    db.add(version)
    db.flush()
    return version, True


def _select_notice_dataset(list_payload: dict[str, Any]) -> str:
    for item in list_payload.get("meta", []):
        if isinstance(item, dict) and item.get("identifier") == NOTICE_IDENTIFIER and item.get("link"):
            return str(item["link"])
    raise CommandError(f"Could not find {NOTICE_IDENTIFIER} in open data list.json.")


class Command(BaseCommand):
    help = "Safely ingest a small open data notices sample for selected RF subjects."

    def add_arguments(self, parser):
        parser.add_argument("--date-from", required=True, help="Inclusive start date, YYYY-MM-DD.")
        parser.add_argument("--date-to", required=True, help="Inclusive end date, YYYY-MM-DD.")
        parser.add_argument(
            "--subjects",
            default=",".join(DEFAULT_SUBJECT_CODES),
            help="Comma-separated subjectEstateCode values. Default: 77,50,40,71.",
        )
        parser.add_argument("--list-url", default=LIST_URL, help=f"Root open data list URL. Default: {LIST_URL}")
        parser.add_argument("--delay", type=float, default=1.0, help="Delay between full notice href requests.")
        parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
        parser.add_argument("--retries", type=int, default=1, help="Retries per HTTP request after the first attempt.")
        parser.add_argument("--retry-delay", type=float, default=3.0, help="Delay before retry in seconds.")
        parser.add_argument(
            "--max-hrefs",
            type=int,
            default=50,
            help="Safety cap for full notice href downloads. Use 0 to disable. Default: 50.",
        )
        parser.add_argument(
            "--report-path",
            default=None,
            help="Optional JSON report path. Defaults to .local/diagnostics/opendata_notice_ingest_<range>.json.",
        )

    def handle(self, *args, **options):
        date_from = _parse_date(options["date_from"], "--date-from")
        date_to = _parse_date(options["date_to"], "--date-to")
        if date_from > date_to:
            raise CommandError("--date-from must be before or equal to --date-to.")

        subject_codes = {code.strip() for code in str(options["subjects"]).split(",") if code.strip()}
        if not subject_codes:
            raise CommandError("--subjects must contain at least one subjectEstateCode.")

        max_hrefs = int(options["max_hrefs"])
        session = requests.Session()

        list_payload, list_status = _fetch_json(
            session,
            options["list_url"],
            timeout=options["timeout"],
            retries=options["retries"],
            retry_delay=options["retry_delay"],
        )
        if list_status != "ok" or not isinstance(list_payload, dict):
            raise CommandError(f"Could not fetch root open data list: status={list_status}")

        meta_url = _select_notice_dataset(list_payload)
        meta_payload, meta_status = _fetch_json(
            session,
            meta_url,
            timeout=options["timeout"],
            retries=options["retries"],
            retry_delay=options["retry_delay"],
        )
        if meta_status != "ok" or not isinstance(meta_payload, dict):
            raise CommandError(f"Could not fetch notice meta.json: status={meta_status} url={meta_url}")

        selected_data_files: list[dict[str, Any]] = []
        for entry in meta_payload.get("data", []):
            if not isinstance(entry, dict) or not entry.get("source"):
                continue
            source_period = _period_from_source(str(entry["source"]))
            if source_period is None:
                continue
            file_start, file_end_exclusive = source_period
            if _period_overlaps(file_start, file_end_exclusive, date_from, date_to):
                selected_data_files.append(
                    {
                        **entry,
                        "source_date": file_start.isoformat(),
                        "coverage_start": file_start.isoformat(),
                        "coverage_end_exclusive": file_end_exclusive.isoformat(),
                        "coverage_kind": _period_kind(file_start, file_end_exclusive),
                    }
                )

        candidates_by_regnum: dict[str, dict[str, Any]] = {}
        data_file_kind_counts: dict[str, int] = {}
        data_files_processed = 0
        total_objects = 0
        period_filtered = 0
        subject_filtered = 0
        notice_type_filtered = 0
        document_type_counts: dict[str, int] = {}
        errors: list[dict[str, Any]] = []

        for data_file in selected_data_files:
            coverage_kind = str(data_file.get("coverage_kind") or "unknown")
            data_file_kind_counts[coverage_kind] = data_file_kind_counts.get(coverage_kind, 0) + 1
            data_url = str(data_file["source"])
            data_payload, data_status = _fetch_json(
                session,
                data_url,
                timeout=options["timeout"],
                retries=options["retries"],
                retry_delay=options["retry_delay"],
            )
            if data_status != "ok" or not isinstance(data_payload, dict):
                errors.append({"stage": "data_file", "url": data_url, "status": data_status})
                continue

            data_files_processed += 1
            list_objects = data_payload.get("listObjects")
            if not isinstance(list_objects, list):
                continue

            for item in list_objects:
                if not isinstance(item, dict):
                    continue
                total_objects += 1
                document_type = str(item.get("documentType") or "")
                document_type_counts[document_type] = document_type_counts.get(document_type, 0) + 1

                publish_dt = _parse_dt(item.get("publishDate"))
                if not publish_dt or not (date_from <= publish_dt.date() <= date_to):
                    continue
                period_filtered += 1

                if str(item.get("subjectEstateCode") or "").strip() not in subject_codes:
                    continue
                subject_filtered += 1

                if item.get("documentType") != "notice":
                    continue
                notice_type_filtered += 1

                regnum = str(item.get("regNum") or "").strip()
                href = str(item.get("href") or "").strip()
                if not regnum or not href:
                    errors.append({"stage": "list_object", "regNum": regnum, "status": "missing_regnum_or_href"})
                    continue

                previous = candidates_by_regnum.get(regnum)
                previous_dt = _parse_dt(previous.get("publishDate")) if previous else None
                if previous is None or (publish_dt and (previous_dt is None or publish_dt >= previous_dt)):
                    candidates_by_regnum[regnum] = {**item, "source_date": data_file["source_date"]}

        candidates = list(candidates_by_regnum.values())
        candidates.sort(key=lambda item: (item.get("publishDate") or "", item.get("regNum") or ""))

        planning_db = SessionLocal()
        try:
            (
                backlog_candidate_pairs,
                hrefs_candidate_valid_versions,
                hrefs_already_processed,
                hrefs_invalid_version_key,
            ) = _effective_backlog_pairs(planning_db, candidates, errors)
        finally:
            planning_db.close()

        selected_candidate_pairs = (
            backlog_candidate_pairs[:max_hrefs]
            if max_hrefs > 0
            else backlog_candidate_pairs
        )

        href_downloaded = 0
        created = 0
        updated = 0
        skipped_existing_same = 0
        ledger_found = 0
        ledger_created = 0
        skipped_processed = 0
        unique_versions_detected = 0
        processed_count = 0

        for item, key_values in selected_candidate_pairs:
            href = str(item["href"])

            unique_versions_detected += 1
            db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                version, was_created = _get_or_create_ledger_entry(db, key_values, now)
                if was_created:
                    ledger_created += 1
                else:
                    ledger_found += 1
                if version.status == "processed":
                    skipped_processed += 1
                    db.commit()
                    continue
                version.status = "downloaded"
                version.error_message = None
                version.downloaded_at = now
                version.updated_at = now
                db.commit()
            except Exception as exc:
                db.rollback()
                errors.append(
                    {
                        "stage": "ledger_prepare",
                        "href": href,
                        "regNum": item.get("regNum"),
                        "status": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                continue
            finally:
                db.close()

            payload, status = _fetch_json(
                session,
                href,
                timeout=options["timeout"],
                retries=options["retries"],
                retry_delay=options["retry_delay"],
            )
            if status != "ok" or not isinstance(payload, dict):
                errors.append({"stage": "href", "href": href, "regNum": item.get("regNum"), "status": status})
                db = SessionLocal()
                try:
                    version, _ = _get_or_create_ledger_entry(db, key_values, datetime.now(timezone.utc))
                    version.status = "failed"
                    version.error_message = status
                    version.updated_at = datetime.now(timezone.utc)
                    db.commit()
                finally:
                    db.close()
                time.sleep(options["delay"])
                continue

            href_downloaded += 1
            fetched_at = datetime.now(timezone.utc)
            values = _notice_values(
                item=item,
                payload=payload,
                fetched_at=fetched_at,
                source_date=str(item.get("source_date") or ""),
            )
            if values is None:
                errors.append({"stage": "payload", "href": href, "regNum": item.get("regNum"), "status": "missing_notice_number"})
                db = SessionLocal()
                try:
                    version, _ = _get_or_create_ledger_entry(db, key_values, datetime.now(timezone.utc))
                    version.status = "failed"
                    version.error_message = "missing_notice_number"
                    version.updated_at = datetime.now(timezone.utc)
                    db.commit()
                finally:
                    db.close()
                time.sleep(options["delay"])
                continue

            db = SessionLocal()
            try:
                notice = db.get(Notice, values["notice_number"])
                if notice is None:
                    notice = Notice(
                        notice_number=values["notice_number"],
                        raw_data=_merge_raw_data({}, values["opendata_payload"], values["opendata_meta"]),
                    )
                    db.add(notice)
                    created += 1
                else:
                    current_raw = _as_dict(notice.raw_data)
                    current_opendata_meta = current_raw.get("opendata_meta")
                    current_opendata_payload = current_raw.get("opendata")
                    if (
                        _meta_without_ingested_at(current_opendata_meta)
                        == _meta_without_ingested_at(values["opendata_meta"])
                        and current_opendata_payload == values["opendata_payload"]
                    ):
                        skipped_existing_same += 1
                    else:
                        updated += 1
                    notice.raw_data = _merge_raw_data(
                        notice.raw_data,
                        values["opendata_payload"],
                        values["opendata_meta"],
                    )

                notice.notice_status = values["notice_status"]
                notice.publish_date = values["publish_date"]
                notice.create_date = values["create_date"]
                notice.update_date = values["update_date"]
                notice.bidd_type_code = values["bidd_type_code"]
                notice.bidd_form_code = values["bidd_form_code"]
                notice.bidder_org_name = values["bidder_org_name"]
                notice.right_holder_name = values["right_holder_name"]
                notice.fetched_at = values["fetched_at"]
                version, _ = _get_or_create_ledger_entry(db, key_values, fetched_at)
                version.status = "processed"
                version.error_message = None
                version.processed_at = fetched_at
                version.downloaded_at = version.downloaded_at or fetched_at
                version.updated_at = fetched_at
                db.commit()
                processed_count += 1
            except Exception as exc:
                db.rollback()
                errors.append(
                    {
                        "stage": "db_write",
                        "href": href,
                        "regNum": item.get("regNum"),
                        "status": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                failed_db = SessionLocal()
                try:
                    version, _ = _get_or_create_ledger_entry(failed_db, key_values, datetime.now(timezone.utc))
                    version.status = "failed"
                    version.error_message = f"{type(exc).__name__}: {exc}"
                    version.updated_at = datetime.now(timezone.utc)
                    failed_db.commit()
                finally:
                    failed_db.close()
            finally:
                db.close()

            time.sleep(options["delay"])

        report_path = Path(options["report_path"] or f".local/diagnostics/opendata_notice_ingest_{date_from}_{date_to}.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "list_url": options["list_url"],
            "meta_url": meta_url,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "subjects": sorted(subject_codes),
            "document_type": "notice",
            "data_files_selected": selected_data_files,
            "data_files_selected_count": len(selected_data_files),
            "data_file_kind_counts": data_file_kind_counts,
            "data_files_processed": data_files_processed,
            "list_objects_total": total_objects,
            "period_filtered": period_filtered,
            "subject_filtered": subject_filtered,
            "notice_type_filtered": notice_type_filtered,
            "unique_regnums_selected": len(candidates),
            "max_hrefs": max_hrefs,
            "hrefs_candidate_total": len(candidates),
            "hrefs_candidate_valid_versions": hrefs_candidate_valid_versions,
            "hrefs_invalid_version_key": hrefs_invalid_version_key,
            "hrefs_already_processed": hrefs_already_processed,
            "hrefs_effective_backlog": len(backlog_candidate_pairs),
            "hrefs_planned_for_batch": len(selected_candidate_pairs),
            "hrefs_planned": len(selected_candidate_pairs),
            "unique_versions_detected": unique_versions_detected,
            "ledger_found": ledger_found,
            "ledger_created": ledger_created,
            "skipped_processed": skipped_processed,
            "hrefs_downloaded": href_downloaded,
            "processed": processed_count,
            "created": created,
            "updated": updated,
            "skipped_existing_same": skipped_existing_same,
            "errors": errors,
            "document_type_counts": document_type_counts,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(f"list_url={options['list_url']}")
        self.stdout.write(f"meta_url={meta_url}")
        self.stdout.write(f"date_from={date_from}")
        self.stdout.write(f"date_to={date_to}")
        self.stdout.write(f"subjects={','.join(sorted(subject_codes))}")
        self.stdout.write(f"data_files_selected={len(selected_data_files)}")
        self.stdout.write(f"data_file_kind_counts={json.dumps(data_file_kind_counts, ensure_ascii=False, sort_keys=True)}")
        for data_file in selected_data_files:
            self.stdout.write(
                "data_file="
                f"{data_file.get('coverage_kind')} "
                f"{data_file.get('coverage_start')}..{data_file.get('coverage_end_exclusive')} "
                f"{data_file.get('source')}"
            )
        self.stdout.write(f"data_files_processed={data_files_processed}")
        self.stdout.write(f"list_objects_total={total_objects}")
        self.stdout.write(f"period_filtered={period_filtered}")
        self.stdout.write(f"subject_filtered={subject_filtered}")
        self.stdout.write(f"notice_type_filtered={notice_type_filtered}")
        self.stdout.write(f"unique_regnums_selected={len(candidates)}")
        self.stdout.write(f"hrefs_candidate_total={len(candidates)}")
        self.stdout.write(f"hrefs_candidate_valid_versions={hrefs_candidate_valid_versions}")
        self.stdout.write(f"hrefs_invalid_version_key={hrefs_invalid_version_key}")
        self.stdout.write(f"hrefs_already_processed={hrefs_already_processed}")
        self.stdout.write(f"hrefs_effective_backlog={len(backlog_candidate_pairs)}")
        self.stdout.write(f"hrefs_planned_for_batch={len(selected_candidate_pairs)}")
        self.stdout.write(f"hrefs_planned={len(selected_candidate_pairs)}")
        self.stdout.write(f"unique_versions_detected={unique_versions_detected}")
        self.stdout.write(f"ledger_found={ledger_found}")
        self.stdout.write(f"ledger_created={ledger_created}")
        self.stdout.write(f"skipped_processed={skipped_processed}")
        self.stdout.write(f"hrefs_downloaded={href_downloaded}")
        self.stdout.write(f"processed={processed_count}")
        self.stdout.write(f"created={created}")
        self.stdout.write(f"updated={updated}")
        self.stdout.write(f"skipped_existing_same={skipped_existing_same}")
        self.stdout.write(f"errors={len(errors)}")
        self.stdout.write(f"report_path={report_path}")
