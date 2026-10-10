from django.conf import settings
from django.db import models

from apps.organizations.models import Organization


class OrganizationBackupSettings(models.Model):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="backup_settings",
    )
    google_email = models.EmailField(blank=True)
    encrypted_refresh_token = models.TextField(blank=True)
    drive_folder_id = models.CharField(max_length=200, blank=True)
    daily_enabled = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_backup_settings",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Backup settings for {self.organization}"


class BackupRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="backup_runs",
    )
    status = models.CharField(max_length=12, choices=Status.choices)
    destination = models.CharField(max_length=12)
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_backup_runs",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at", "-pk")

    def __str__(self):
        return f"{self.organization} backup ({self.status})"
