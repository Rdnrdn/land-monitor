from django.contrib import admin

from .models import Lot, Region, UserLot


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "torgi_region_code", "is_active", "sort_order")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)
    readonly_fields = [field.name for field in Region._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "source_lot_id",
        "title",
        "region_display_admin",
        "cadastre_number",
        "price_min",
        "application_deadline",
        "is_active",
        "is_finished",
    )
    search_fields = (
        "id",
        "source_lot_id",
        "title",
        "cadastre_number",
        "region",
        "region_name",
        "district",
        "address",
    )
    list_filter = ("source", "region_ref", "is_active", "is_finished", "segment", "price_bucket")
    readonly_fields = [field.name for field in Lot._meta.fields]

    @admin.display(description="Регион")
    def region_display_admin(self, obj: Lot):
        return obj.region_display

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserLot)
class UserLotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lot",
        "user_status",
        "is_favorite",
        "needs_inspection",
        "needs_legal_check",
        "deposit_paid",
        "updated_at",
    )
    search_fields = (
        "id",
        "comment",
        "lot__source_lot_id",
        "lot__title",
        "lot__cadastre_number",
    )
    list_filter = (
        "user_status",
        "is_favorite",
        "needs_inspection",
        "needs_legal_check",
        "deposit_paid",
    )
    raw_id_fields = ("lot",)
    readonly_fields = ("created_at", "updated_at")
