from django.contrib import admin

from .models import BackupRun, OrganizationBackupSettings


@admin.register(OrganizationBackupSettings)
class OrganizationBackupSettingsAdmin(admin.ModelAdmin):
    list_display = ("organization", "google_email", "daily_enabled", "updated_at")
    readonly_fields = ("encrypted_refresh_token",)


@admin.register(BackupRun)
class BackupRunAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "status",
        "destination",
        "file_name",
        "started_at",
        "completed_at",
    )
    list_filter = ("organization", "status", "destination")
    readonly_fields = (
        "organization",
        "status",
        "destination",
        "file_name",
        "file_size",
        "error_message",
        "started_by",
        "started_at",
        "completed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
