import re
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Role
from apps.organizations.models import Organization

from .models import BackupRun, OrganizationBackupSettings
from .services import (
    BackupError,
    build_google_authorization_url,
    create_database_backup,
    encrypt_refresh_token,
    exchange_authorization_code,
    google_account_email,
    google_drive_is_configured,
)

OAUTH_STATE_SALT = "agriculture-pos-google-drive-oauth"


def _organization_queryset(user):
    organizations = Organization.objects.filter(is_active=True)
    if user.is_superuser:
        return organizations.distinct()
    return organizations.filter(
        branches__memberships__user=user,
        branches__memberships__role__name=Role.ADMIN,
        branches__is_active=True,
    ).distinct()


def _authorized_organization(user, organization_id):
    try:
        organization_id = int(organization_id)
    except (TypeError, ValueError) as exc:
        raise NotFound("Organization not found.") from exc
    if organization_id < 1:
        raise NotFound("Organization not found.")
    return get_object_or_404(
        _organization_queryset(user),
        pk=organization_id,
    )


def _serialize_settings(organization, user):
    config = OrganizationBackupSettings.objects.filter(
        organization=organization
    ).first()
    latest = BackupRun.objects.filter(organization=organization).first()
    return {
        "organization_id": organization.pk,
        "organization_name": organization.name,
        "google_drive_configured": google_drive_is_configured(),
        "google_email": config.google_email if config else "",
        "drive_connected": bool(config and config.encrypted_refresh_token),
        "drive_folder_id": config.drive_folder_id if config else "",
        "daily_enabled": config.daily_enabled if config else False,
        "manual_backup_allowed": user.is_superuser or Organization.objects.count() == 1,
        "daily_backup_supported": Organization.objects.count() == 1,
        "latest_backup": (
            {
                "status": latest.status,
                "destination": latest.destination,
                "file_name": latest.file_name,
                "file_size": latest.file_size,
                "error_message": latest.error_message,
                "started_at": latest.started_at,
                "completed_at": latest.completed_at,
            }
            if latest
            else None
        ),
        "recent_backups": [
            {
                "id": run.pk,
                "status": run.status,
                "destination": run.destination,
                "file_name": run.file_name,
                "file_size": run.file_size,
                "error_message": run.error_message,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
            }
            for run in BackupRun.objects.filter(organization=organization)[:10]
        ],
    }


class OrganizationBackupListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        organizations = _organization_queryset(request.user)
        return Response(
            [_serialize_settings(organization, request.user) for organization in organizations]
        )


class OrganizationBackupSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_id):
        organization = _authorized_organization(request.user, organization_id)
        return Response(_serialize_settings(organization, request.user))

    def patch(self, request, organization_id):
        organization = _authorized_organization(request.user, organization_id)
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Provide settings as a JSON object."})
        allowed_fields = {"daily_enabled", "drive_folder_id"}
        unexpected_fields = set(request.data) - allowed_fields
        if unexpected_fields:
            raise ValidationError(
                {"detail": "Only daily_enabled and drive_folder_id can be changed here."}
            )

        config, _ = OrganizationBackupSettings.objects.get_or_create(
            organization=organization
        )
        if "daily_enabled" in request.data:
            daily_enabled = request.data["daily_enabled"]
            if not isinstance(daily_enabled, bool):
                raise ValidationError({"daily_enabled": "Choose on or off."})
            if daily_enabled and not config.encrypted_refresh_token:
                raise ValidationError(
                    {"daily_enabled": "Connect a Google Drive account first."}
                )
            if daily_enabled and not google_drive_is_configured():
                raise ValidationError(
                    {"daily_enabled": "Google Drive OAuth credentials are not configured."}
                )
            if daily_enabled and Organization.objects.count() != 1:
                raise ValidationError(
                    {
                        "daily_enabled": (
                            "Automatic whole-database backups are currently limited "
                            "to installations with one organization."
                        )
                    }
                )
            config.daily_enabled = daily_enabled
        if "drive_folder_id" in request.data:
            folder_id = request.data["drive_folder_id"]
            if (
                not isinstance(folder_id, str)
                or len(folder_id) > 200
                or (folder_id and not re.fullmatch(r"[A-Za-z0-9_-]+", folder_id))
            ):
                raise ValidationError(
                    {"drive_folder_id": "Enter a valid Google Drive folder ID."}
                )
            config.drive_folder_id = folder_id
        config.updated_by = request.user
        config.save()
        return Response(_serialize_settings(organization, request.user))


class StartGoogleDriveOAuthView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Provide an organization ID."})
        organization_id = request.data.get("organization_id")
        organization = _authorized_organization(request.user, organization_id)
        state = signing.dumps(
            {"user_id": request.user.pk, "organization_id": organization.pk},
            salt=OAUTH_STATE_SALT,
        )
        try:
            authorization_url = build_google_authorization_url(state)
        except BackupError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"authorization_url": authorization_url})


class DisconnectGoogleDriveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, organization_id):
        organization = _authorized_organization(request.user, organization_id)
        config = OrganizationBackupSettings.objects.filter(
            organization=organization
        ).first()
        if config:
            config.google_email = ""
            config.encrypted_refresh_token = ""
            config.daily_enabled = False
            config.updated_by = request.user
            config.save(
                update_fields=(
                    "google_email",
                    "encrypted_refresh_token",
                    "daily_enabled",
                    "updated_by",
                    "updated_at",
                )
            )
        return Response(_serialize_settings(organization, request.user))


class GoogleDriveOAuthCallbackView(APIView):
    permission_classes = []

    def get(self, request):
        result = "error"
        detail = "Google Drive connection was not completed."
        try:
            if request.query_params.get("error"):
                raise BackupError("Google Drive authorization was cancelled or denied.")
            state = signing.loads(
                request.query_params.get("state", ""),
                salt=OAUTH_STATE_SALT,
                max_age=600,
            )
            user_id = state["user_id"]
            organization_id = state["organization_id"]
            if (
                not request.user.is_authenticated
                or request.user.pk != user_id
            ):
                raise BackupError(
                    "Your shop session ended during Google sign-in. Sign in again "
                    "and reconnect Drive."
                )
            organization = _authorized_organization(request.user, organization_id)
            code = request.query_params.get("code")
            if not code:
                raise BackupError("Google did not return an authorization code.")
            token_data = exchange_authorization_code(code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            if not access_token:
                raise BackupError("Google did not return an access token.")
            config, _ = OrganizationBackupSettings.objects.get_or_create(
                organization=organization
            )
            if not refresh_token:
                if not config.encrypted_refresh_token:
                    raise BackupError(
                        "Google did not return a refresh token. Revoke this app in "
                        "your Google Account permissions and connect again."
                    )
            else:
                config.encrypted_refresh_token = encrypt_refresh_token(refresh_token)
            config.google_email = google_account_email(access_token)
            config.updated_by = request.user
            config.save()
            result = "connected"
            detail = "Google Drive is connected."
        except (BackupError, signing.BadSignature, KeyError, TypeError) as exc:
            detail = str(exc) if isinstance(exc, BackupError) else (
                "Google Drive sign-in expired or could not be verified. Please try again."
            )

        redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/settings?{urlencode({'google_drive': result, 'message': detail})}"
        return HttpResponseRedirect(redirect_url)


class TemporaryBackupResponse(FileResponse):
    def __init__(self, backup_path: Path, filename: str):
        self.backup_path = backup_path
        super().__init__(
            backup_path.open("rb"),
            as_attachment=True,
            filename=filename,
            content_type="application/octet-stream",
        )

    def close(self):
        try:
            super().close()
        finally:
            self.backup_path.unlink(missing_ok=True)


class DownloadDatabaseBackupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_id):
        organization = _authorized_organization(request.user, organization_id)
        if not request.user.is_superuser and Organization.objects.count() != 1:
            raise PermissionDenied(
                "A full database backup is available only to the system "
                "administrator when this installation has one organization."
            )
        run = BackupRun.objects.create(
            organization=organization,
            status=BackupRun.Status.RUNNING,
            destination="download",
            started_by=request.user,
        )
        try:
            backup_path, filename, file_size = create_database_backup()
        except BackupError as exc:
            run.status = BackupRun.Status.FAILED
            run.error_message = str(exc)
            run.completed_at = timezone.now()
            run.save(
                update_fields=("status", "error_message", "completed_at")
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        run.status = BackupRun.Status.SUCCEEDED
        run.file_name = filename
        run.file_size = file_size
        run.completed_at = timezone.now()
        run.save(
            update_fields=("status", "file_name", "file_size", "completed_at")
        )
        return TemporaryBackupResponse(backup_path, filename)


def google_drive_callback(request):
    return GoogleDriveOAuthCallbackView.as_view()(request)
