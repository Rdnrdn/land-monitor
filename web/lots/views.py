import json
import uuid
from collections import Counter
from datetime import date, datetime
from functools import cached_property

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import DetailView, ListView

from .models import Lot, Region, UserLot, UserLotStatus
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
DEAL_TYPE_LABELS = {
    "sale": "Продажа",
    "rent": "Аренда",
}


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


def _get_lot_deal_type(lot: Lot) -> str | None:
    raw_data = lot.raw_data if isinstance(lot.raw_data, dict) else {}
    deal_type = raw_data.get("typeTransaction")
    if deal_type in DEAL_TYPE_LABELS:
        return DEAL_TYPE_LABELS[deal_type]
    return deal_type


def _build_lot_detail_rows(lot: Lot, *, canonical_municipality_label: str | None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {"label": "ID", "value": lot.id},
        {"label": "Источник", "value": lot.source},
        {"label": "ID лота в источнике", "value": lot.source_lot_id},
    ]

    if _has_detail_value(lot.region_display):
        rows.append({"label": "Регион", "value": lot.region_display})

    municipality_value = canonical_municipality_label or lot.municipality_name
    if _has_detail_value(municipality_value):
        rows.append({"label": "Муниципалитет", "value": municipality_value})

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
        ("FIAS GUID", lot.fias_guid),
        ("Кадастровый номер", lot.cadastre_number),
        ("Площадь, м²", lot.area_m2),
        ("Категория", lot.category),
        ("Тип сделки", _get_lot_deal_type(lot)),
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

    notice_rows = [
        notice_row
        for notice_row in (
            _build_notice_row("Номер извещения", notice_number),
            _build_notice_row("Статус извещения", notice_status),
            _build_notice_row("Дата публикации", publish_date),
            _build_notice_row("Дата создания", create_date),
            _build_notice_row("Дата обновления", update_date),
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


class LotListView(LoginRequiredMixin, ListView):
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
    ) -> Lot.objects.none().__class__:
        queryset = Lot.objects.select_related("user_lot", "region_ref", "municipality_ref")

        price_min = self.request.GET.get("price_min")
        if price_min:
            queryset = queryset.filter(price_min__gte=price_min)

        price_max = self.request.GET.get("price_max")
        if price_max:
            queryset = queryset.filter(price_min__lte=price_max)

        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(lot_status_external=status)

        if self.selected_region is not None:
            queryset = queryset.filter(region_ref=self.selected_region)

        if apply_municipality_filter and self.show_municipality_filter and self.selected_municipality_aliases:
            queryset = queryset.filter(
                Q(municipality_ref__normalized_name__in=self.selected_municipality_aliases)
                | Q(municipality_name__in=self.selected_municipality_raw_aliases)
            )

        if apply_deal_type_filter and self.is_deal_type_filter_active:
            queryset = queryset.filter(raw_data__typeTransaction__in=self.selected_deal_types)

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
        return Region.objects.filter(region_query).order_by("sort_order", "name").first()

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
    def municipality_option_counts(self) -> dict[str, int]:
        if not self.show_municipality_filter:
            return {}

        normalized_alias_map = moscow_oblast_safe_normalized_alias_map()
        raw_alias_map = moscow_oblast_safe_raw_alias_map()
        counts: Counter[str] = Counter()

        rows = self._build_queryset(
            apply_municipality_filter=False,
            apply_deal_type_filter=True,
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
        ).values_list("raw_data__typeTransaction", flat=True)
        for deal_type in rows.iterator():
            if deal_type in DEAL_TYPE_LABELS:
                counts[deal_type] += 1
        return dict(counts)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for lot in context["lots"]:
            lot.user_lot_state = _get_user_lot_state(lot)

        base_queryset = Lot.objects.all()
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
            Region.objects.filter(is_active=True).order_by("sort_order", "name")
        )
        context["selected_region"] = self.selected_region
        context["show_municipality_filter"] = self.show_municipality_filter
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
            "status",
            "region",
            "is_active",
        )
        context["active_filter_count"] = sum(
            1 for param in active_filter_params if self.request.GET.get(param)
        ) + len(self.selected_municipality_slugs) + (1 if self.is_deal_type_filter_active else 0) + (1 if current_tab != "all" else 0)
        context["has_active_filters"] = context["active_filter_count"] > 0
        return context


class LotDetailView(LoginRequiredMixin, DetailView):
    model = Lot
    template_name = "lots/lot_detail.html"
    context_object_name = "lot"
    queryset = Lot.objects.select_related("user_lot", "region_ref", "municipality_ref")

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
        context["detail_rows"] = _build_lot_detail_rows(
            self.object,
            canonical_municipality_label=canonical_municipality_label,
        )
        context["detail_date_rows"] = _build_lot_detail_date_rows(self.object)
        context.update(_build_lot_notice_context(self.object))
        return context


class LotQuickActionView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        lot = get_object_or_404(Lot, pk=pk)
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
