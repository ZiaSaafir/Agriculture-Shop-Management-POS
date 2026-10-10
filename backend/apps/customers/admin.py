from django.contrib import admin

from .models import Customer, CustomerLedgerEntry


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "organization", "is_active", "created_at")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "phone", "organization__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CustomerLedgerEntry)
class CustomerLedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "customer_name_snapshot",
        "branch",
        "entry_type",
        "amount",
        "created_by",
    )
    list_filter = ("organization", "branch", "entry_type")
    search_fields = (
        "customer_name_snapshot",
        "customer__name",
        "reference",
        "reason",
    )
    readonly_fields = (
        "organization",
        "customer",
        "branch",
        "entry_type",
        "amount",
        "reason",
        "reference",
        "customer_name_snapshot",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
