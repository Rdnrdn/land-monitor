from django.contrib import admin

from .models import Lot, UserLot


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "source_lot_id",
        "title",
        "region",
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
        "district",
        "address",
    )
    list_filter = ("source", "region", "is_active", "is_finished", "segment", "price_bucket")
    readonly_fields = [field.name for field in Lot._meta.fields]

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
