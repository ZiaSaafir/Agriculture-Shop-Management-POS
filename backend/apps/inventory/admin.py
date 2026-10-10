from django.contrib import admin

from .models import StockBalance, StockMovement


@admin.register(StockBalance)
class StockBalanceAdmin(admin.ModelAdmin):
    list_display = ("branch", "product", "on_hand", "updated_at")
    list_filter = ("branch__organization", "branch")
    search_fields = ("product__name", "product__sku", "branch__name")
    readonly_fields = ("branch", "product", "on_hand", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "branch",
        "product",
        "product_name_snapshot",
        "unit_symbol_snapshot",
        "movement_type",
        "quantity",
        "created_by",
    )
    list_filter = ("branch__organization", "branch", "movement_type")
    search_fields = ("product__name", "product__sku", "reason", "reference")
    readonly_fields = (
        "branch",
        "product",
        "movement_type",
        "quantity",
        "reason",
        "reference",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
