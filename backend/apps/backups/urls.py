from django.urls import path

from .api import (
    DownloadDatabaseBackupView,
    DisconnectGoogleDriveView,
    OrganizationBackupListView,
    OrganizationBackupSettingsView,
    StartGoogleDriveOAuthView,
    google_drive_callback,
)

app_name = "backups"

urlpatterns = [
    path("organizations/", OrganizationBackupListView.as_view(), name="organizations"),
    path(
        "organizations/<int:organization_id>/",
        OrganizationBackupSettingsView.as_view(),
        name="organization-settings",
    ),
    path(
        "organizations/<int:organization_id>/download/",
        DownloadDatabaseBackupView.as_view(),
        name="download",
    ),
    path(
        "organizations/<int:organization_id>/google/disconnect/",
        DisconnectGoogleDriveView.as_view(),
        name="google-disconnect",
    ),
    path("google/start/", StartGoogleDriveOAuthView.as_view(), name="google-start"),
    path("google/callback/", google_drive_callback, name="google-callback"),
]
