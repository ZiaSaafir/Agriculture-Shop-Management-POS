from django.contrib import admin

from .models import Supplier, SupplierLedgerEntry


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "organization", "is_active", "created_at")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "phone", "account_reference", "organization__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SupplierLedgerEntry)
class SupplierLedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "supplier_name_snapshot",
        "branch",
        "entry_type",
        "amount",
        "created_by",
    )
    list_filter = ("organization", "branch", "entry_type")
    search_fields = (
        "supplier_name_snapshot",
        "supplier__name",
        "reference",
        "reason",
    )
    readonly_fields = (
        "organization",
        "supplier",
        "branch",
        "entry_type",
        "amount",
        "reason",
        "reference",
        "supplier_name_snapshot",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
