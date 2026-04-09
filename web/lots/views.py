import uuid
from functools import cached_property

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import DetailView, ListView

from .models import Lot, Municipality, Region, UserLot, UserLotStatus


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
MOSCOW_OBLAST_SLUG = "moskovskaya-oblast"


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

    def get_queryset(self):
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

        if self.show_municipality_filter and self.selected_municipalities:
            queryset = queryset.filter(municipality_ref__in=self.selected_municipalities)

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

        return queryset.order_by(self.get_ordering_value(), "-id")

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
        return [value for value in self.request.GET.getlist("municipality") if value]

    @cached_property
    def municipality_options(self) -> list[Municipality]:
        if not self.show_municipality_filter or self.selected_region is None:
            return []
        return list(
            Municipality.objects.filter(
                region=self.selected_region,
                is_active=True,
            ).order_by("sort_order", "name")
        )

    @cached_property
    def selected_municipalities(self) -> list[Municipality]:
        if not self.selected_municipality_slugs:
            return []
        return list(
            Municipality.objects.filter(
                region=self.selected_region,
                slug__in=self.selected_municipality_slugs,
                is_active=True,
            )
        )

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
        context["municipality_options"] = self.municipality_options
        context["selected_municipality_slugs"] = self.selected_municipality_slugs
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
        ) + len(self.selected_municipality_slugs) + (1 if current_tab != "all" else 0)
        context["has_active_filters"] = context["active_filter_count"] > 0
        return context


class LotDetailView(LoginRequiredMixin, DetailView):
    model = Lot
    template_name = "lots/lot_detail.html"
    context_object_name = "lot"
    queryset = Lot.objects.select_related("user_lot")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_lot"] = _get_user_lot_state(self.object)
        context["user_status_choices"] = STATUS_CHOICES
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
