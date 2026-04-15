import json
import re
import uuid
from collections import Counter
from datetime import date, datetime
from functools import cached_property

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import DetailView, ListView

from .auth_utils import OptionalLoginRequiredMixin
from .models import Lot, Notice, Region, Subject, UserLot, UserLotStatus
from .safe_municipalities import (
    MOSCOW_OBLAST_SLUG,
    SafeMunicipalityOption,
    get_safe_municipality_options_for_region_slug,
    get_safe_municipality_label,
    moscow_oblast_safe_option_map,
    moscow_oblast_safe_normalized_alias_map,
    moscow_oblast_safe_raw_alias_map,
)


ALLOWED_ORDERINGS = {
    "-updated_at": "-updated_at",
    "price_min": "price_min",
    "-price_min": "-price_min",
    "application_deadline": "application_deadline",
    "-application_deadline": "-application_deadline",
    "score": "score",
    "-score": "-score",
}

IN_PROGRESS_STATUSES = (
    UserLotStatus.REVIEW,
    UserLotStatus.PLAN,
    UserLotStatus.APPLIED,
    UserLotStatus.BIDDING,
)

TAB_OPTIONS = (
    ("all", "Все"),
    ("favorites", "Избранное"),
    ("in_progress", "В работе"),
    ("needs_check", "На проверку"),
    ("archive", "Архив"),
)

STATUS_CHOICES = tuple(UserLotStatus.choices)
VALID_USER_STATUSES = {choice for choice, _ in STATUS_CHOICES}
DEFAULT_PER_PAGE = 25
PER_PAGE_OPTIONS = (25, 50, 100)
MOSCOW_OBLAST_RF_CODE = "50"
HIDDEN_REGION_SLUGS = {"leningradskaya-oblast"}
DEAL_TYPE_LABELS = {
    "sale": "Продажа",
    "rent": "Аренда",
}
SUBJECT_RF_LABELS = {
    "40": "Калужская область",
    "47": "Ленинградская область",
    "50": "Московская область",
    "61": "Ростовская область",
    "69": "Тверская область",
    "71": "Тульская область",
    "77": "Москва",
}
LOW_SIGNAL_LOTCARD_VALUES = {
    "согласно извещению",
    "согласно извещению о проведении аукциона",
    "не указано",
    "отсутствует",
    "-",
    "—",
}
LOTCARD_ATTRIBUTE_LABELS = {
    "обременения реализуемого имущества": "Обременения",
    "срок и порядок внесения задатка": "Срок и порядок внесения задатка",
    "порядок ознакомления с имуществом": "Порядок ознакомления с имуществом",
    "срок заключения договора": "Срок заключения договора",
    "условия договора, заключаемого по результатам торгов": "Условия договора",
}


def _notice_lots_jsonb_sql(raw_data_expression: str = "raw_data") -> str:
    lots_expression = (
        f"{raw_data_expression}->'opendata'->'exportObject'->'structuredObject'"
        "->'notice'->'lots'"
    )
    return (
        "CASE "
        f"WHEN jsonb_typeof({lots_expression}) = 'array' THEN {lots_expression} "
        "ELSE '[]'::jsonb "
        "END"
    )


def _lot_product_scope_q() -> Q:
    return Q(source="opendata_notice", source_notice_bidd_type_code="ZK")


def _scoped_lot_queryset():
    return Lot.objects.filter(_lot_product_scope_q())


def _mo_opendata_zk_queryset():
    return Lot.objects.filter(
        source="opendata_notice",
        source_notice_bidd_type_code="ZK",
        subject_rf_code=MOSCOW_OBLAST_RF_CODE,
    )


def _clean_distinct_values(queryset, field_name: str) -> list[str]:
    return list(
        queryset.exclude(**{f"{field_name}__isnull": True})
        .exclude(**{field_name: ""})
        .order_by(field_name)
        .values_list(field_name, flat=True)
        .distinct()
    )


def _updated_querystring(request, **updates: str | None) -> str:
    query = request.GET.copy()
    for key, value in updates.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()


def _get_user_lot_state(lot: Lot) -> UserLot | None:
    try:
        return lot.user_lot
    except ObjectDoesNotExist:
        return None


def _get_next_url(request: HttpRequest, lot: Lot) -> str:
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse("lots:detail", args=[lot.pk])


def _create_user_lot(lot: Lot) -> UserLot:
    now = timezone.now()
    return UserLot.objects.create(
        id=uuid.uuid4(),
        lot=lot,
        user_status=UserLotStatus.NEW,
        is_favorite=False,
        needs_inspection=False,
        needs_legal_check=False,
        deposit_paid=False,
        created_at=now,
        updated_at=now,
    )


def _get_or_create_user_lot(lot: Lot) -> tuple[UserLot, bool]:
    existing = _get_user_lot_state(lot)
    if existing is not None:
        return existing, False

    try:
        with transaction.atomic():
            return _create_user_lot(lot), True
    except IntegrityError:
        return UserLot.objects.get(lot=lot), False


def _has_detail_value(value) -> bool:
    return value is not None and value != ""


def _clean_display_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "value", "fullName"):
            cleaned = _clean_display_text(value.get(key))
            if cleaned:
                return cleaned
        return None
    if isinstance(value, list):
        parts = [_clean_display_text(item) for item in value]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None

    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if not cleaned or cleaned.casefold() in {"none", "null"}:
        return None
    return cleaned


def _display_text_key(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _get_lot_estate_address_display(lot: Lot, lotcard_data: dict | None = None) -> str | None:
    raw_data = lot.raw_data if isinstance(lot.raw_data, dict) else {}
    lotcard_data = lotcard_data if isinstance(lotcard_data, dict) else _get_lotcard_snapshot(lot)
    estate_address = _clean_display_text(
        lotcard_data.get("estateAddress") or raw_data.get("estateAddress")
    )
    if not estate_address:
        return None
    if lot.address and _display_text_key(lot.address) == _display_text_key(estate_address):
        return None
    return estate_address


def _get_lot_deal_type(lot: Lot) -> str | None:
    raw_data = lot.raw_data if isinstance(lot.raw_data, dict) else {}
    deal_type = raw_data.get("typeTransaction")
    if deal_type in DEAL_TYPE_LABELS:
        return DEAL_TYPE_LABELS[deal_type]
    return deal_type


def _get_lot_contract_type_bucket_display(lot: Lot) -> str | None:
    bucket = _clean_display_text(lot.contract_type_bucket)
    if bucket in DEAL_TYPE_LABELS:
        return DEAL_TYPE_LABELS[bucket]
    return bucket


def _get_lot_contract_type_source_display(lot: Lot) -> str | None:
    source_name = _clean_display_text(lot.contract_type_source_name)
    deal_type_display = _get_lot_contract_type_bucket_display(lot)
    if source_name and deal_type_display and _display_text_key(source_name) == _display_text_key(deal_type_display):
        return None
    return source_name


def _get_lot_deal_type_display(lot: Lot) -> str | None:
    return _get_lot_contract_type_bucket_display(lot) or _get_lot_deal_type(lot)


def _resolve_deal_type_value(
    contract_type_bucket: object,
    raw_type_transaction: object,
) -> str | None:
    bucket = _clean_display_text(contract_type_bucket)
    if bucket in DEAL_TYPE_LABELS:
        return bucket

    raw_value = _clean_display_text(raw_type_transaction)
    if raw_value in DEAL_TYPE_LABELS:
        return raw_value
    return None


def _get_lotcard_deal_type(lotcard_data: dict) -> str | None:
    deal_type = lotcard_data.get("typeTransaction")
    if deal_type in DEAL_TYPE_LABELS:
        return DEAL_TYPE_LABELS[deal_type]
    return _clean_display_text(deal_type)


def _is_useful_lotcard_text(value: object) -> bool:
    cleaned = _clean_display_text(value)
    if not cleaned:
        return False
    return cleaned.casefold() not in LOW_SIGNAL_LOTCARD_VALUES


def _parse_lotcard_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    parsed = parse_datetime(value)
    return parsed


def _format_money(value: object) -> str | None:
    if value in (None, ""):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return _clean_display_text(value)
    return f"{amount:,.2f} руб.".replace(",", " ")


def _is_valid_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _build_display_row(
    label: str,
    value: object,
    *,
    is_date: bool = False,
    is_url: bool = False,
) -> dict[str, object] | None:
    if not _has_detail_value(value):
        return None
    return {
        "label": label,
        "value": value,
        "is_date": is_date,
        "is_url": is_url,
    }


def _get_lotcard_snapshot(lot: Lot) -> dict:
    raw_data = lot.raw_data if isinstance(lot.raw_data, dict) else {}
    lotcard_data = raw_data.get("lotcard")
    if not isinstance(lotcard_data, dict):
        return {}
    nested_data = lotcard_data.get("data")
    if isinstance(nested_data, dict):
        return nested_data
    return lotcard_data


def _subject_rf_display(lotcard_data: dict) -> str | None:
    code = _clean_display_text(lotcard_data.get("subjectRFCode"))
    name = _clean_display_text(lotcard_data.get("subjectRFName"))
    if not name and code:
        name = SUBJECT_RF_LABELS.get(code)
    if name and code:
        return f"{name} ({code})"
    return name or (f"код {code}" if code else None)


def _point_display(lotcard_data: dict) -> str | None:
    point = lotcard_data.get("point")
    if not isinstance(point, dict):
        return None
    lat = point.get("lat")
    lon = point.get("lon")
    if lat in (None, "") or lon in (None, ""):
        return None
    return f"{lat}, {lon}"


def _lotcard_attribute_label(full_name: str) -> str | None:
    normalized = _display_text_key(full_name)
    for needle, label in LOTCARD_ATTRIBUTE_LABELS.items():
        if needle in normalized:
            return label
    if "ознаком" in normalized and ("имуществ" in normalized or "схем" in normalized):
        return "Порядок ознакомления с имуществом"
    return None


def _lotcard_attribute_rows(lotcard_data: dict) -> list[dict[str, object]]:
    attributes = lotcard_data.get("attributes")
    if not isinstance(attributes, list):
        return []

    rows: list[dict[str, object]] = []
    seen_labels: set[str] = set()
    for item in attributes:
        if not isinstance(item, dict):
            continue
        full_name = _clean_display_text(item.get("fullName"))
        if not full_name:
            continue
        label = _lotcard_attribute_label(full_name)
        value = _clean_display_text(item.get("value"))
        if not label or not _is_useful_lotcard_text(value) or label in seen_labels:
            continue
        rows.append({"label": label, "value": value, "is_date": False, "is_url": False})
        seen_labels.add(label)
    return rows


def _build_lotcard_rows(
    lot: Lot,
    lotcard_data: dict | None,
) -> list[dict[str, object]]:
    if not isinstance(lotcard_data, dict):
        return []

    rows: list[dict[str, object]] = []

    def add(row: dict[str, object] | None) -> None:
        if row is not None:
            rows.append(row)

    if lot.deposit_amount is None:
        add(_build_display_row("Задаток", _format_money(lotcard_data.get("deposit"))))

    date_fields = (
        ("Дата начала торгов", "auctionStartDate", lot.auction_date),
        ("Начало подачи заявок", "biddStartTime", lot.application_start_date),
        ("Окончание подачи заявок", "biddEndTime", lot.application_deadline),
    )
    for label, key, existing_value in date_fields:
        if existing_value:
            continue
        value = _parse_lotcard_datetime(lotcard_data.get(key))
        add(_build_display_row(label, value, is_date=True))

    if not _get_lot_deal_type(lot):
        add(_build_display_row("Тип сделки", _get_lotcard_deal_type(lotcard_data)))

    etp_url = lotcard_data.get("etpUrl")
    if _is_valid_url(etp_url):
        add(_build_display_row("Ссылка на площадку", etp_url, is_url=True))

    add(_build_display_row("Субъект местонахождения имущества", _subject_rf_display(lotcard_data)))
    add(_build_display_row("Координаты", _point_display(lotcard_data)))

    lot_description = _clean_display_text(lotcard_data.get("lotDescription"))
    if (
        lot_description
        and lot.title
        and _display_text_key(lot_description) != _display_text_key(lot.title)
        and (not lot.description or _display_text_key(lot_description) != _display_text_key(lot.description))
    ):
        add(_build_display_row("Описание lotcard", lot_description))

    rows.extend(_lotcard_attribute_rows(lotcard_data))
    return rows


def _build_lot_detail_rows(
    lot: Lot,
    *,
    canonical_municipality_label: str | None,
    estate_address_display: str | None,
) -> list[dict[str, object]]:
    deal_type_display = _get_lot_deal_type_display(lot)
    contract_type_source_display = _get_lot_contract_type_source_display(lot)
    rows: list[dict[str, object]] = [
        {"label": "ID", "value": lot.id},
        {"label": "Источник", "value": lot.source},
        {"label": "ID лота в источнике", "value": lot.source_lot_id},
    ]

    if lot.subject_ref_id and lot.subject_ref and _has_detail_value(lot.subject_ref.name):
        rows.append({"label": "Субъект РФ", "value": lot.subject_ref.name})

    if _has_detail_value(lot.region_display):
        rows.append({"label": "Регион", "value": lot.region_display})

    municipality_value = canonical_municipality_label or lot.municipality_name
    if _has_detail_value(municipality_value):
        rows.append({"label": "Муниципалитет", "value": municipality_value})

    for label, value in (
        ("ФИАС уровень 3", lot.fias_level_3_name),
        ("ФИАС уровень 5", lot.fias_level_5_name),
        ("ФИАС уровень 6", lot.fias_level_6_name),
    ):
        if _has_detail_value(value):
            rows.append({"label": label, "value": value})

    region_code = (
        lot.region_ref.torgi_region_code
        if lot.region_ref_id and lot.region_ref
        else lot.subject_rf_code
    )
    if _has_detail_value(region_code):
        rows.append({"label": "Код региона torgi.gov.ru", "value": region_code})

    optional_rows = (
        ("Район", lot.district),
        ("Адрес", lot.address),
        ("Местонахождение имущества", estate_address_display),
        ("FIAS GUID", lot.fias_guid),
        ("Кадастровый номер", lot.cadastre_number),
        ("Площадь, м²", lot.area_m2),
        ("Категория", lot.category),
        ("Тип сделки", deal_type_display),
        ("Вид договора", contract_type_source_display),
        ("Форма собственности", lot.ownership_form_name),
        ("Разрешённое использование", lot.permitted_use),
        ("Начальная цена", lot.price_min),
        ("Итоговая цена", lot.price_fin),
        ("Размер задатка", lot.deposit_amount),
        ("Валюта", lot.currency_code),
        ("ETP", lot.etp_name or lot.etp_code),
        ("Организатор", lot.organizer_name),
        ("ИНН организатора", lot.organizer_inn),
        ("КПП организатора", lot.organizer_kpp),
        ("Статус лота", lot.lot_status_external),
        ("Ценовой диапазон", lot.price_bucket),
        ("Дней до дедлайна", lot.days_to_deadline),
        ("Score", lot.score),
        ("Сегмент", lot.segment),
        ("Ограничения", lot.land_restrictions_text),
        ("Срок подписания договора", lot.contract_sign_period_text),
        ("Описание", lot.description),
    )
    for label, value in optional_rows:
        if _has_detail_value(value):
            rows.append({"label": label, "value": value})

    return rows


def _build_lot_detail_date_rows(lot: Lot) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, value in (
        ("Начало приёма заявок", lot.application_start_date),
        ("Окончание приёма заявок", lot.application_deadline),
        ("Дата торгов", lot.auction_date),
        ("Создано в источнике", lot.source_created_at),
        ("Обновлено в источнике", lot.source_updated_at),
    ):
        if _has_detail_value(value):
            rows.append({"label": label, "value": value})
    return rows


def _build_notice_row(label: str, value: object) -> dict[str, object] | None:
    if not _has_detail_value(value):
        return None
    return {
        "label": label,
        "value": value,
        "is_date": isinstance(value, (date, datetime)),
        "is_url": isinstance(value, str) and value.startswith(("http://", "https://")),
    }


def _notice_attachments(raw_data: object) -> list[dict[str, object]]:
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw_data, dict):
        return []
    attachments = raw_data.get("attachments")
    if not isinstance(attachments, list):
        return []

    documents: list[dict[str, object]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        title = item.get("fileName")
        doc_type = item.get("attachmentTypeName")
        size = item.get("fileSize")
        uploaded_at = item.get("uploadDate")
        if not any(_has_detail_value(value) for value in (title, doc_type, size, uploaded_at)):
            continue
        documents.append(
            {
                "title": title,
                "type": doc_type,
                "size": size,
                "uploaded_at": uploaded_at,
            }
        )
    return documents


def _notice_additional_detail_value(raw_data: object, detail_code: str) -> str | None:
    notice_payload = _get_opendata_notice_payload(raw_data)
    additional_details = notice_payload.get("additionalDetails")
    if not isinstance(additional_details, list):
        return None

    for item in additional_details:
        if not isinstance(item, dict):
            continue
        if item.get("code") != detail_code:
            continue
        return _clean_display_text(item.get("value"))
    return None


def _build_lot_notice_context(lot: Lot) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                n.notice_number,
                n.notice_status,
                n.publish_date,
                n.create_date,
                n.update_date,
                n.application_portal_url,
                n.auction_site_url,
                n.raw_data
            FROM lots AS l
            LEFT JOIN notices AS n ON n.notice_number = l.notice_number
            WHERE l.id = %s
            LIMIT 1
            """,
            [lot.pk],
        )
        row = cursor.fetchone()

    if row is None:
        return {
            "notice_rows": [],
            "notice_documents": [],
            "notice_source_url": None,
        }

    (
        notice_number,
        notice_status,
        publish_date,
        create_date,
        update_date,
        application_portal_url,
        auction_site_url,
        raw_data,
    ) = row

    notice_payload = _get_opendata_notice_payload(raw_data)
    bidd_conditions = notice_payload.get("biddConditions")
    if not isinstance(bidd_conditions, dict):
        bidd_conditions = {}

    bidd_start_at = parse_datetime(bidd_conditions.get("biddStartTime", ""))
    bidd_end_at = parse_datetime(bidd_conditions.get("biddEndTime", ""))
    application_address = _notice_additional_detail_value(
        raw_data,
        "DA_applicationAddressRules_IPS(ZK)",
    )

    notice_rows = [
        notice_row
        for notice_row in (
            _build_notice_row("Номер извещения", notice_number),
            _build_notice_row("Статус извещения", notice_status),
            _build_notice_row("Дата публикации", publish_date),
            _build_notice_row("Дата создания", create_date),
            _build_notice_row("Дата обновления", update_date),
            _build_notice_row("Начало приёма заявок", bidd_start_at),
            _build_notice_row("Окончание приёма заявок", bidd_end_at),
            _build_notice_row("Адрес подачи заявлений", application_address),
            _build_notice_row("Портал подачи заявки", application_portal_url),
            _build_notice_row("Площадка торгов", auction_site_url),
        )
        if notice_row is not None
    ]

    notice_source_url = next(
        (
            value
            for value in (application_portal_url, auction_site_url, lot.source_url)
            if _has_detail_value(value)
        ),
        None,
    )

    return {
        "notice_rows": notice_rows,
        "notice_documents": _notice_attachments(raw_data),
        "notice_source_url": notice_source_url,
    }


def _get_opendata_notice_payload(raw_data: object) -> dict:
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw_data, dict):
        return {}

    opendata = raw_data.get("opendata")
    if not isinstance(opendata, dict):
        return {}

    export_object = opendata.get("exportObject")
    if not isinstance(export_object, dict):
        export_object = {}
    structured_object = export_object.get("structuredObject")
    if not isinstance(structured_object, dict):
        structured_object = {}
    notice = structured_object.get("notice")
    if isinstance(notice, dict):
        return notice
    if isinstance(opendata.get("notice"), dict):
        return opendata["notice"]
    return {}


def _get_opendata_notice_lots(raw_data: object) -> list[dict]:
    notice = _get_opendata_notice_payload(raw_data)
    lots = notice.get("lots")
    if not isinstance(lots, list):
        return []
    return [item for item in lots if isinstance(item, dict)]


def _notice_lot_subject(lot_data: dict) -> tuple[str | None, str | None]:
    bidding_object_info = lot_data.get("biddingObjectInfo")
    if not isinstance(bidding_object_info, dict):
        return None, None
    subject = bidding_object_info.get("subjectRF")
    if not isinstance(subject, dict):
        return None, None
    return _clean_display_text(subject.get("code")), _clean_display_text(subject.get("name"))


def _notice_lot_address(lot_data: dict) -> str | None:
    bidding_object_info = lot_data.get("biddingObjectInfo")
    if isinstance(bidding_object_info, dict):
        address = _clean_display_text(bidding_object_info.get("estateAddress"))
        if address:
            return address
    return _clean_display_text(lot_data.get("estateAddress"))


def _notice_display_title(notice: Notice, notice_payload: dict) -> str:
    common_info = notice_payload.get("commonInfo")
    if isinstance(common_info, dict):
        for key in ("procedureName", "name", "biddTypeName", "biddFormName"):
            value = _clean_display_text(common_info.get(key))
            if value:
                return value

        for key in ("biddType", "biddForm"):
            value = _clean_display_text(common_info.get(key))
            if value:
                return value

    for key in ("noticeName", "name"):
        value = _clean_display_text(notice_payload.get(key))
        if value:
            return value
    return f"Извещение {notice.notice_number}"


def _attach_notice_list_display(notice: Notice) -> None:
    notice_payload = _get_opendata_notice_payload(notice.raw_data)
    lots = _get_opendata_notice_lots(notice.raw_data)

    subjects: dict[str, str] = {}
    addresses: list[str] = []
    has_documents = False
    has_images = False

    for lot_data in lots:
        subject_code, subject_name = _notice_lot_subject(lot_data)
        if subject_code:
            subjects[subject_code] = subject_name or subject_code

        address = _notice_lot_address(lot_data)
        if address and address not in addresses:
            addresses.append(address)

        docs = lot_data.get("docs")
        if isinstance(docs, list) and docs:
            has_documents = True

        image_ids = lot_data.get("imageIds")
        if isinstance(image_ids, list) and image_ids:
            has_images = True

    notice.display_title = _notice_display_title(notice, notice_payload)
    notice.lot_count = len(lots)
    notice.subject_summary = ", ".join(
        f"{name} ({code})" for code, name in sorted(subjects.items())
    )
    notice.address_summary = "; ".join(addresses[:3])
    notice.has_documents = has_documents
    notice.has_images = has_images


class NoticeListView(OptionalLoginRequiredMixin, ListView):
    model = Notice
    template_name = "lots/notice_list.html"
    context_object_name = "notices"
    page_size = DEFAULT_PER_PAGE

    @cached_property
    def selected_subject_codes(self) -> list[str]:
        valid_codes = set(Subject.objects.values_list("code", flat=True))
        values: list[str] = []
        for value in self.request.GET.getlist("subject"):
            cleaned = (value or "").strip()
            if not cleaned or cleaned not in valid_codes or cleaned in values:
                continue
            values.append(cleaned)
        return values

    def get_queryset(self):
        queryset = Notice.objects.extra(where=["raw_data ? %s"], params=["opendata"])
        if self.selected_subject_codes:
            placeholders = ", ".join(["%s"] * len(self.selected_subject_codes))
            lots_sql = _notice_lots_jsonb_sql()
            queryset = queryset.extra(
                where=[
                    f"""
                    EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements({lots_sql}) AS lot_obj
                        WHERE lot_obj->'biddingObjectInfo'->'subjectRF'->>'code' IN ({placeholders})
                    )
                    """
                ],
                params=self.selected_subject_codes,
            )
        return queryset.order_by("-publish_date", "-fetched_at", "notice_number")

    @cached_property
    def current_page(self) -> int:
        raw_value = self.request.GET.get("page")
        try:
            page = int(raw_value)
        except (TypeError, ValueError):
            return 1
        return page if page > 0 else 1

    @cached_property
    def subject_option_counts(self) -> dict[str, int]:
        # Counting subjects from raw_data->opendata->notice->lots for every request
        # forces a full JSONB scan on production-sized data. Keep the filter itself,
        # but drop counts from the synchronous render path.
        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.pop("paginator", None)
        context.pop("page_obj", None)
        context.pop("is_paginated", None)

        offset = (self.current_page - 1) * self.page_size
        page_slice = list(self.object_list[offset : offset + self.page_size + 1])
        has_next = len(page_slice) > self.page_size
        notices = page_slice[: self.page_size]

        context["notices"] = notices
        context["object_list"] = notices
        context["page_number"] = self.current_page
        context["per_page"] = self.page_size
        context["has_previous"] = self.current_page > 1
        context["has_next"] = has_next
        context["previous_page_querystring"] = (
            _updated_querystring(self.request, page=self.current_page - 1)
            if self.current_page > 1
            else ""
        )
        context["next_page_querystring"] = (
            _updated_querystring(self.request, page=self.current_page + 1)
            if has_next
            else ""
        )

        for notice in notices:
            _attach_notice_list_display(notice)

        context["subject_options"] = [
            {
                "label": subject.name,
                "value": subject.code,
                "count": None,
                "selected": subject.code in self.selected_subject_codes,
            }
            for subject in Subject.objects.filter(published=True).order_by("code", "name")
        ]
        context["selected_subjects"] = self.selected_subject_codes
        context["page_querystring"] = _updated_querystring(self.request, page=None)
        return context


class NoticeDetailView(OptionalLoginRequiredMixin, DetailView):
    model = Notice
    template_name = "lots/notice_detail.html"
    context_object_name = "notice"
    pk_url_kwarg = "notice_number"

    def get_queryset(self):
        return Notice.objects.extra(where=["raw_data ? %s"], params=["opendata"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        _attach_notice_list_display(self.object)
        next_url = self.request.GET.get("next")
        if not (
            next_url
            and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={self.request.get_host()},
                require_https=self.request.is_secure(),
            )
        ):
            next_url = reverse("notices")

        context["notice_back_url"] = next_url
        context["notice_rows"] = [
            row
            for row in (
                _build_notice_row("Номер извещения", self.object.notice_number),
                _build_notice_row("Дата публикации", self.object.publish_date),
                _build_notice_row("Дата извещения", self.object.create_date),
                _build_notice_row("Дата обновления", self.object.update_date),
                _build_notice_row("Лотов внутри", self.object.lot_count),
                _build_notice_row("Субъекты по лотам", self.object.subject_summary),
            )
            if row is not None
        ]
        return context


class LotListView(OptionalLoginRequiredMixin, ListView):
    model = Lot
    template_name = "lots/lot_list.html"
    context_object_name = "lots"
    paginate_by = DEFAULT_PER_PAGE

    def get_paginate_by(self, queryset):
        raw_per_page = self.request.GET.get("per_page")
        try:
            per_page = int(raw_per_page)
        except (TypeError, ValueError):
            return DEFAULT_PER_PAGE
        return per_page if per_page in PER_PAGE_OPTIONS else DEFAULT_PER_PAGE

    def _build_queryset(
        self,
        *,
        apply_municipality_filter: bool,
        apply_deal_type_filter: bool,
        apply_subject_filter: bool,
        apply_fias_filter: bool,
    ) -> Lot.objects.none().__class__:
        queryset = _scoped_lot_queryset().select_related(
            "user_lot",
            "region_ref",
            "municipality_ref",
            "subject_ref",
        )

        price_min = self.request.GET.get("price_min")
        if price_min:
            queryset = queryset.filter(price_min__gte=price_min)

        price_max = self.request.GET.get("price_max")
        if price_max:
            queryset = queryset.filter(price_min__lte=price_max)

        deadline_from = self.request.GET.get("deadline_from")
        if deadline_from:
            queryset = queryset.filter(application_deadline__gte=deadline_from)

        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(lot_status_external=status)

        if self.selected_region is not None:
            region_code = (self.selected_region.subject_rf_code or "").strip()
            if region_code:
                queryset = queryset.filter(subject_rf_code=region_code)
            else:
                queryset = queryset.none()

        if apply_subject_filter and self.selected_subject_codes:
            queryset = queryset.filter(subject_ref__code__in=self.selected_subject_codes)

        if apply_municipality_filter and self.show_municipality_filter and self.selected_municipality_aliases:
            queryset = queryset.filter(
                Q(municipality_ref__normalized_name__in=self.selected_municipality_aliases)
                | Q(municipality_name__in=self.selected_municipality_raw_aliases)
            )

        if apply_fias_filter and self.show_fias_filter:
            precise_q = Q()
            if self.selected_fias_level_5_guids:
                precise_q |= Q(fias_level_5_guid__in=self.selected_fias_level_5_guids)
            if self.selected_fias_level_6_guids:
                precise_q |= Q(fias_level_6_guid__in=self.selected_fias_level_6_guids)

            if precise_q:
                queryset = queryset.filter(precise_q)
            elif self.selected_fias_level_3_guids:
                queryset = queryset.filter(fias_level_3_guid__in=self.selected_fias_level_3_guids)

        if apply_deal_type_filter and self.is_deal_type_filter_active:
            queryset = queryset.filter(
                Q(contract_type_bucket__in=self.selected_deal_types)
                | (
                    (Q(contract_type_bucket__isnull=True) | Q(contract_type_bucket=""))
                    & Q(raw_data__typeTransaction__in=self.selected_deal_types)
                )
            )

        if self.location_query:
            queryset = queryset.filter(
                Q(title__icontains=self.location_query)
                | Q(raw_data__lotcard__estateAddress__icontains=self.location_query)
                | Q(address__icontains=self.location_query)
                | Q(district__icontains=self.location_query)
                | Q(raw_data__estateAddress__icontains=self.location_query)
            )

        is_active = self.request.GET.get("is_active")
        if is_active == "true":
            queryset = queryset.filter(is_active=True)
        elif is_active == "false":
            queryset = queryset.filter(is_active=False)

        tab = self.get_current_tab()
        if tab == "favorites":
            queryset = queryset.filter(user_lot__is_favorite=True)
        elif tab == "in_progress":
            queryset = queryset.filter(user_lot__user_status__in=IN_PROGRESS_STATUSES)
        elif tab == "needs_check":
            queryset = queryset.filter(
                Q(user_lot__needs_inspection=True) | Q(user_lot__needs_legal_check=True)
            )
        elif tab == "archive":
            queryset = queryset.filter(
                Q(user_lot__user_status=UserLotStatus.ARCHIVE) | Q(is_active=False)
            )

        return queryset

    def get_queryset(self):
        return self._build_queryset(
            apply_municipality_filter=True,
            apply_deal_type_filter=True,
            apply_subject_filter=True,
            apply_fias_filter=True,
        ).order_by(
            self.get_ordering_value(),
            "-id",
        )

    def get_current_tab(self) -> str:
        tab = self.request.GET.get("tab", "all")
        return tab if tab in dict(TAB_OPTIONS) else "all"

    @cached_property
    def selected_region(self) -> Region | None:
        raw_region = self.request.GET.get("region")
        if not raw_region:
            return None
        region_query = Q(slug=raw_region) | Q(name=raw_region)
        if raw_region.isdigit():
            region_query |= Q(torgi_region_code=int(raw_region))
            region_query |= Q(subject_rf_code=raw_region)
        return Region.objects.filter(region_query).order_by("sort_order", "name").first()

    @cached_property
    def selected_subject_codes(self) -> list[str]:
        valid_codes = set(Subject.objects.values_list("code", flat=True))
        values: list[str] = []
        for value in self.request.GET.getlist("subject"):
            cleaned = (value or "").strip()
            if not cleaned or cleaned not in valid_codes or cleaned in values:
                continue
            values.append(cleaned)
        return values

    def get_ordering_value(self) -> str:
        ordering = self.request.GET.get("ordering", "-updated_at")
        return ALLOWED_ORDERINGS.get(ordering, "-updated_at")

    @cached_property
    def show_municipality_filter(self) -> bool:
        return bool(
            self.selected_region is not None
            and self.selected_region.slug == MOSCOW_OBLAST_SLUG
        )

    @cached_property
    def show_fias_filter(self) -> bool:
        return self.show_municipality_filter

    @cached_property
    def mo_fias_level_3_options(self) -> list[dict[str, str]]:
        if not self.show_fias_filter:
            return []
        rows = (
            _mo_opendata_zk_queryset()
            .exclude(fias_level_3_guid__isnull=True)
            .exclude(fias_level_3_guid="")
            .exclude(fias_level_3_name__isnull=True)
            .exclude(fias_level_3_name="")
            .order_by("fias_level_3_name", "fias_level_3_guid")
            .values_list("fias_level_3_guid", "fias_level_3_name")
            .distinct()
        )
        return [{"guid": guid, "name": name} for guid, name in rows]

    def _selected_fias_guids(self, param_name: str, valid_guids: set[str]) -> list[str]:
        if not self.show_fias_filter:
            return []
        values: list[str] = []
        for value in self.request.GET.getlist(param_name):
            cleaned = (value or "").strip()
            if not cleaned or cleaned not in valid_guids or cleaned in values:
                continue
            values.append(cleaned)
        return values

    @cached_property
    def selected_fias_level_3_guids(self) -> list[str]:
        valid_guids = {option["guid"] for option in self.mo_fias_level_3_options}
        return self._selected_fias_guids("fias_level_3", valid_guids)

    @cached_property
    def mo_fias_tree(self) -> list[dict[str, object]]:
        if not self.show_fias_filter:
            return []

        rows = (
            _mo_opendata_zk_queryset()
            .exclude(fias_level_3_guid__isnull=True)
            .exclude(fias_level_3_guid="")
            .exclude(fias_level_3_name__isnull=True)
            .exclude(fias_level_3_name="")
            .order_by(
                "fias_level_3_name",
                "fias_level_5_name",
                "fias_level_6_name",
                "fias_level_5_guid",
                "fias_level_6_guid",
            )
            .values_list(
                "fias_level_3_guid",
                "fias_level_3_name",
                "fias_level_5_guid",
                "fias_level_5_name",
                "fias_level_6_guid",
                "fias_level_6_name",
            )
            .distinct()
        )

        tree_by_guid: dict[str, dict[str, object]] = {}
        for level_3_guid, level_3_name, level_5_guid, level_5_name, level_6_guid, level_6_name in rows:
            node = tree_by_guid.setdefault(
                level_3_guid,
                {
                    "guid": level_3_guid,
                    "name": level_3_name,
                    "children": [],
                    "_child_keys": set(),
                },
            )

            for child_guid, child_name, level_code in (
                (level_5_guid, level_5_name, 5),
                (level_6_guid, level_6_name, 6),
            ):
                if not child_guid or not child_name:
                    continue
                child_key = (level_code, child_guid)
                if child_key in node["_child_keys"]:
                    continue
                node["_child_keys"].add(child_key)
                node["children"].append(
                    {
                        "guid": child_guid,
                        "name": child_name,
                        "level": level_code,
                    }
                )

        tree: list[dict[str, object]] = []
        for node in tree_by_guid.values():
            node["children"].sort(key=lambda item: (item["name"], item["guid"]))
            node.pop("_child_keys", None)
            tree.append(node)
        tree.sort(key=lambda item: (item["name"], item["guid"]))
        return tree

    @cached_property
    def _mo_fias_child_guid_sets(self) -> tuple[set[str], set[str]]:
        level_5_guids: set[str] = set()
        level_6_guids: set[str] = set()
        for node in self.mo_fias_tree:
            for child in node["children"]:
                if child["level"] == 5:
                    level_5_guids.add(child["guid"])
                elif child["level"] == 6:
                    level_6_guids.add(child["guid"])
        return level_5_guids, level_6_guids

    @cached_property
    def selected_fias_level_5_guids(self) -> list[str]:
        level_5_guids, _ = self._mo_fias_child_guid_sets
        return self._selected_fias_guids("fias_level_5", level_5_guids)

    @cached_property
    def selected_fias_level_6_guids(self) -> list[str]:
        _, level_6_guids = self._mo_fias_child_guid_sets
        return self._selected_fias_guids("fias_level_6", level_6_guids)

    @cached_property
    def selected_municipality_slugs(self) -> list[str]:
        if not self.show_municipality_filter:
            return []
        option_map = moscow_oblast_safe_option_map()
        values: list[str] = []
        for value in self.request.GET.getlist("municipality"):
            if not value or value not in option_map or value in values:
                continue
            values.append(value)
        return values

    @cached_property
    def municipality_options(self) -> list[SafeMunicipalityOption]:
        if not self.show_municipality_filter or self.selected_region is None:
            return []
        return get_safe_municipality_options_for_region_slug(self.selected_region.slug)

    @cached_property
    def selected_municipality_options(self) -> list[SafeMunicipalityOption]:
        if not self.selected_municipality_slugs:
            return []
        option_map = moscow_oblast_safe_option_map()
        return [
            option_map[value]
            for value in self.selected_municipality_slugs
            if value in option_map
        ]

    @cached_property
    def selected_municipality_aliases(self) -> list[str]:
        aliases: list[str] = []
        for option in self.selected_municipality_options:
            aliases.extend(option.normalized_aliases)
        return list(dict.fromkeys(aliases))

    @cached_property
    def selected_municipality_raw_aliases(self) -> list[str]:
        aliases: list[str] = []
        for option in self.selected_municipality_options:
            aliases.extend(option.aliases)
        return list(dict.fromkeys(aliases))

    @cached_property
    def selected_deal_types(self) -> list[str]:
        values: list[str] = []
        for value in self.request.GET.getlist("deal_type"):
            if value not in DEAL_TYPE_LABELS or value in values:
                continue
            values.append(value)
        return values or list(DEAL_TYPE_LABELS.keys())

    @cached_property
    def is_deal_type_filter_active(self) -> bool:
        return set(self.selected_deal_types) != set(DEAL_TYPE_LABELS.keys())

    @cached_property
    def location_query(self) -> str:
        return (self.request.GET.get("location") or "").strip()

    @cached_property
    def municipality_option_counts(self) -> dict[str, int]:
        if not self.show_municipality_filter:
            return {}

        normalized_alias_map = moscow_oblast_safe_normalized_alias_map()
        raw_alias_map = moscow_oblast_safe_raw_alias_map()
        counts: Counter[str] = Counter()

        rows = self._build_queryset(
            apply_municipality_filter=False,
            apply_deal_type_filter=True,
            apply_subject_filter=True,
            apply_fias_filter=True,
        ).values_list(
            "municipality_ref__normalized_name",
            "municipality_name",
        )
        for normalized_name, raw_name in rows.iterator():
            matched_values: set[str] = set()

            if normalized_name:
                safe_value = normalized_alias_map.get(normalized_name)
                if safe_value:
                    matched_values.add(safe_value)

            if raw_name:
                safe_value = raw_alias_map.get(raw_name)
                if safe_value:
                    matched_values.add(safe_value)

            for safe_value in matched_values:
                counts[safe_value] += 1

        return dict(counts)

    @cached_property
    def deal_type_option_counts(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        rows = self._build_queryset(
            apply_municipality_filter=True,
            apply_deal_type_filter=False,
            apply_subject_filter=True,
            apply_fias_filter=True,
        ).values_list("contract_type_bucket", "raw_data__typeTransaction")
        for contract_type_bucket, raw_type_transaction in rows.iterator():
            deal_type = _resolve_deal_type_value(contract_type_bucket, raw_type_transaction)
            if deal_type in DEAL_TYPE_LABELS:
                counts[deal_type] += 1
        return dict(counts)

    @cached_property
    def subject_option_counts(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        rows = self._build_queryset(
            apply_municipality_filter=True,
            apply_deal_type_filter=True,
            apply_subject_filter=False,
            apply_fias_filter=True,
        ).values_list("subject_ref__code", flat=True)
        for subject_code in rows.iterator():
            if subject_code:
                counts[subject_code] += 1
        return dict(counts)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for lot in context["lots"]:
            lot.user_lot_state = _get_user_lot_state(lot)
            lot.deal_type_display = _get_lot_deal_type_display(lot)
            lot.deal_type_source_display = _get_lot_contract_type_source_display(lot)

        base_queryset = _scoped_lot_queryset()
        current_tab = self.get_current_tab()
        current_ordering = self.request.GET.get("ordering", "-updated_at")
        page_obj = context["page_obj"]
        paginator = page_obj.paginator
        municipality_query_update = {} if self.show_municipality_filter else {"municipality": None}
        elided_pages = paginator.get_elided_page_range(
            number=page_obj.number,
            on_each_side=1,
            on_ends=1,
        )

        context["tab_options"] = [
            {
                "value": value,
                "label": label,
                "is_active": value == current_tab,
                "querystring": _updated_querystring(
                    self.request,
                    tab=value,
                    page=None,
                    **municipality_query_update,
                ),
            }
            for value, label in TAB_OPTIONS
        ]
        context["ordering_options"] = [
            ("-updated_at", "Сначала новые"),
            ("price_min", "Цена: по возрастанию"),
            ("-price_min", "Цена: по убыванию"),
            ("application_deadline", "Дедлайн: ближе"),
            ("-application_deadline", "Дедлайн: дальше"),
            ("score", "Score: по возрастанию"),
            ("-score", "Score: по убыванию"),
        ]
        context["current_tab"] = current_tab
        context["current_ordering"] = (
            current_ordering if current_ordering in ALLOWED_ORDERINGS else "-updated_at"
        )
        context["current_ordering_label"] = dict(context["ordering_options"]).get(
            context["current_ordering"],
            "Сначала новые",
        )
        context["per_page_options"] = PER_PAGE_OPTIONS
        context["current_per_page"] = self.get_paginate_by(self.object_list)
        context["region_options"] = list(
            Region.objects.filter(is_active=True)
            .exclude(slug__in=HIDDEN_REGION_SLUGS)
            .order_by("sort_order", "name")
        )
        context["selected_region"] = self.selected_region
        context["subject_options"] = [
            {
                "label": subject.name,
                "value": subject.code,
                "count": self.subject_option_counts.get(subject.code, 0),
                "selected": subject.code in self.selected_subject_codes,
            }
            for subject in Subject.objects.filter(published=True).order_by("code", "name")
        ]
        context["selected_subjects"] = self.selected_subject_codes
        context["location_query"] = self.location_query
        context["show_municipality_filter"] = self.show_municipality_filter
        context["show_fias_filter"] = self.show_fias_filter
        context["mo_fias_level_3_options"] = self.mo_fias_level_3_options
        context["mo_fias_tree"] = self.mo_fias_tree
        context["selected_fias_level_3_guids"] = self.selected_fias_level_3_guids
        context["selected_fias_level_5_guids"] = self.selected_fias_level_5_guids
        context["selected_fias_level_6_guids"] = self.selected_fias_level_6_guids
        context["municipality_options"] = [
            {
                "label": option.label,
                "value": option.value,
                "count": self.municipality_option_counts.get(option.value, 0),
                "selected": option.value in self.selected_municipality_slugs,
            }
            for option in self.municipality_options
        ]
        context["selected_municipality_slugs"] = self.selected_municipality_slugs
        context["selected_municipality_options"] = self.selected_municipality_options
        context["deal_type_options"] = [
            {
                "label": label,
                "value": value,
                "count": self.deal_type_option_counts.get(value, 0),
                "selected": value in self.selected_deal_types,
            }
            for value, label in DEAL_TYPE_LABELS.items()
        ]
        context["selected_deal_types"] = self.selected_deal_types
        context["status_options"] = _clean_distinct_values(base_queryset, "lot_status_external")
        context["page_querystring"] = _updated_querystring(
            self.request,
            page=None,
            **municipality_query_update,
        )
        context["pagination_links"] = [
            {
                "label": page,
                "number": page if isinstance(page, int) else None,
                "is_current": page == page_obj.number,
                "is_ellipsis": page == paginator.ELLIPSIS,
                "querystring": _updated_querystring(
                    self.request,
                    page=page,
                    **municipality_query_update,
                )
                if isinstance(page, int)
                else "",
            }
            for page in elided_pages
        ]
        context["user_status_choices"] = STATUS_CHOICES
        active_filter_params = (
            "price_min",
            "price_max",
            "deadline_from",
            "status",
            "region",
            "is_active",
            "location",
        )
        context["active_filter_count"] = sum(
            1 for param in active_filter_params if self.request.GET.get(param)
        )
        context["active_filter_count"] += len(self.selected_subject_codes)
        context["active_filter_count"] += len(self.selected_municipality_slugs)
        context["active_filter_count"] += len(self.selected_fias_level_3_guids)
        context["active_filter_count"] += len(self.selected_fias_level_5_guids)
        context["active_filter_count"] += len(self.selected_fias_level_6_guids)
        context["active_filter_count"] += 1 if self.is_deal_type_filter_active else 0
        context["active_filter_count"] += 1 if current_tab != "all" else 0
        context["has_active_filters"] = context["active_filter_count"] > 0
        return context


class LotDetailView(OptionalLoginRequiredMixin, DetailView):
    model = Lot
    template_name = "lots/lot_detail.html"
    context_object_name = "lot"
    queryset = _scoped_lot_queryset().select_related(
        "user_lot",
        "region_ref",
        "municipality_ref",
        "subject_ref",
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_lot"] = _get_user_lot_state(self.object)
        context["user_status_choices"] = STATUS_CHOICES
        canonical_municipality_label = get_safe_municipality_label(
            region_slug=self.object.region_ref.slug if self.object.region_ref_id and self.object.region_ref else None,
            normalized_name=(
                self.object.municipality_ref.normalized_name
                if self.object.municipality_ref_id and self.object.municipality_ref
                else None
            ),
            raw_name=self.object.municipality_name,
        )
        context["canonical_municipality_label"] = canonical_municipality_label
        lotcard_data = _get_lotcard_snapshot(self.object)
        estate_address_display = _get_lot_estate_address_display(self.object, lotcard_data)
        context["estate_address_display"] = estate_address_display
        context["detail_rows"] = _build_lot_detail_rows(
            self.object,
            canonical_municipality_label=canonical_municipality_label,
            estate_address_display=estate_address_display,
        )
        context["detail_date_rows"] = _build_lot_detail_date_rows(self.object)
        context["lotcard_rows"] = _build_lotcard_rows(self.object, lotcard_data)
        context.update(_build_lot_notice_context(self.object))
        return context


class LotQuickActionView(OptionalLoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        lot = get_object_or_404(_scoped_lot_queryset(), pk=pk)
        action = request.POST.get("action", "")

        if action == "set_status":
            return self._set_status(request, lot)
        if action == "toggle_favorite":
            return self._toggle_bool(
                request,
                lot,
                field_name="is_favorite",
                success_text="Избранное обновлено.",
            )
        if action == "toggle_needs_inspection":
            return self._toggle_bool(
                request,
                lot,
                field_name="needs_inspection",
                success_text="Флаг осмотра обновлён.",
            )
        if action == "toggle_needs_legal_check":
            return self._toggle_bool(
                request,
                lot,
                field_name="needs_legal_check",
                success_text="Флаг юр. проверки обновлён.",
            )
        if action == "toggle_deposit_paid":
            return self._toggle_bool(
                request,
                lot,
                field_name="deposit_paid",
                success_text="Статус задатка обновлён.",
            )

        messages.error(request, "Неизвестное действие.")
        return redirect(_get_next_url(request, lot))

    def _set_status(self, request: HttpRequest, lot: Lot) -> HttpResponseRedirect:
        user_status = request.POST.get("user_status", "")
        if user_status not in VALID_USER_STATUSES:
            messages.error(request, "Недопустимый статус.")
            return redirect(_get_next_url(request, lot))

        user_lot, created = _get_or_create_user_lot(lot)
        user_lot.user_status = user_status
        user_lot.updated_at = timezone.now()
        user_lot.save(update_fields=["user_status", "updated_at"])

        if created:
            messages.success(request, "User state создан, статус обновлён.")
        else:
            messages.success(request, "Статус обновлён.")
        return redirect(_get_next_url(request, lot))

    def _toggle_bool(
        self,
        request: HttpRequest,
        lot: Lot,
        *,
        field_name: str,
        success_text: str,
    ) -> HttpResponseRedirect:
        user_lot, created = _get_or_create_user_lot(lot)
        current_value = bool(getattr(user_lot, field_name))
        setattr(user_lot, field_name, not current_value)
        user_lot.updated_at = timezone.now()
        user_lot.save(update_fields=[field_name, "updated_at"])

        if created:
            messages.success(request, "User state создан.")
        else:
            messages.info(request, success_text)
        return redirect(_get_next_url(request, lot))
