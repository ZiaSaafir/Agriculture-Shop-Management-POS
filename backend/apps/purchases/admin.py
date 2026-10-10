from django.contrib import admin

from .models import (
    Purchase,
    PurchaseLine,
    PurchaseReturn,
    PurchaseReturnLine,
    SupplierPayment,
    SupplierPaymentAllocation,
)


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "product_name_snapshot",
        "sku_snapshot",
        "unit_symbol_snapshot",
        "quantity",
        "unit_cost",
        "subtotal",
        "discount_amount",
        "tax_amount",
        "total",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "purchase_number",
        "purchase_date",
        "supplier_name_snapshot",
        "branch",
        "status",
        "total",
        "created_by",
    )
    list_filter = ("organization", "branch", "status", "purchase_date")
    search_fields = (
        "supplier_name_snapshot",
        "supplier_invoice_number",
        "supplier__name",
    )
    readonly_fields = (
        "organization",
        "branch",
        "supplier",
        "supplier_name_snapshot",
        "supplier_invoice_number",
        "purchase_date",
        "notes",
        "status",
        "subtotal",
        "discount_total",
        "tax_total",
        "total",
        "created_by",
        "posted_by",
        "posted_at",
        "created_at",
        "updated_at",
    )
    inlines = (PurchaseLineInline,)

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PurchaseReturnLineInline(admin.TabularInline):
    model = PurchaseReturnLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "purchase_line",
        "product",
        "product_name_snapshot",
        "sku_snapshot",
        "unit_symbol_snapshot",
        "quantity",
        "credit_amount",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = (
        "return_number",
        "return_date",
        "supplier_name_snapshot",
        "purchase",
        "branch",
        "status",
        "credit_total",
        "created_by",
    )
    list_filter = ("organization", "branch", "status", "return_date")
    search_fields = (
        "supplier_name_snapshot",
        "supplier_credit_note_reference",
        "purchase__supplier_invoice_number",
    )
    readonly_fields = (
        "organization",
        "branch",
        "purchase",
        "supplier",
        "supplier_name_snapshot",
        "supplier_credit_note_reference",
        "return_date",
        "notes",
        "status",
        "credit_total",
        "created_by",
        "posted_by",
        "posted_at",
        "created_at",
        "updated_at",
    )
    inlines = (PurchaseReturnLineInline,)

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SupplierPaymentAllocationInline(admin.TabularInline):
    model = SupplierPaymentAllocation
    extra = 0
    can_delete = False
    readonly_fields = (
        "purchase",
        "purchase_number_snapshot",
        "amount",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "payment_number",
        "payment_date",
        "supplier_name_snapshot",
        "branch",
        "amount",
        "payment_method",
        "reference",
        "created_by",
    )
    list_filter = ("organization", "branch", "payment_date", "payment_method")
    search_fields = (
        "supplier_name_snapshot",
        "supplier__name",
        "reference",
    )
    readonly_fields = (
        "organization",
        "branch",
        "supplier",
        "supplier_name_snapshot",
        "amount",
        "payment_date",
        "payment_method",
        "reference",
        "notes",
        "created_by",
        "created_at",
    )
    inlines = (SupplierPaymentAllocationInline,)

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
