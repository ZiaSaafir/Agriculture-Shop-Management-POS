from django.contrib import admin

from .models import Sale, SaleLine, SalesReturn, SalesReturnLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "product_name_snapshot",
        "sku_snapshot",
        "unit_symbol_snapshot",
        "quantity",
        "unit_price",
        "subtotal",
        "discount_amount",
        "tax_amount",
        "total",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "sale_number",
        "sale_date",
        "customer_name_snapshot",
        "branch",
        "status",
        "total",
        "amount_paid",
        "created_by",
    )
    list_filter = ("organization", "branch", "status", "sale_date")
    search_fields = ("customer_name_snapshot", "items__product_name_snapshot")
    readonly_fields = (
        "organization",
        "branch",
        "customer",
        "customer_name_snapshot",
        "sale_date",
        "notes",
        "status",
        "subtotal",
        "discount_total",
        "tax_total",
        "total",
        "amount_paid",
        "payment_method",
        "payment_reference",
        "created_by",
        "completed_by",
        "completed_at",
        "created_at",
        "updated_at",
    )
    inlines = (SaleLineInline,)

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SalesReturnLineInline(admin.TabularInline):
    model = SalesReturnLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "sale_line",
        "product_name_snapshot",
        "sku_snapshot",
        "unit_symbol_snapshot",
        "quantity",
        "base_quantity",
        "credit_amount",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SalesReturn)
class SalesReturnAdmin(admin.ModelAdmin):
    list_display = ("return_number", "sale", "branch", "disposition", "total", "return_date")
    list_filter = ("branch__organization", "branch", "disposition", "return_date")
    readonly_fields = (
        "organization",
        "branch",
        "sale",
        "disposition",
        "return_date",
        "total",
        "notes",
        "created_by",
        "created_at",
    )
    inlines = (SalesReturnLineInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
