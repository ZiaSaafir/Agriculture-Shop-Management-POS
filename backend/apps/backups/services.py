import base64
import hashlib
import http.client
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone


class BackupError(Exception):
    pass


def google_drive_is_configured():
    return bool(
        settings.GOOGLE_DRIVE_CLIENT_ID
        and settings.GOOGLE_DRIVE_CLIENT_SECRET
        and settings.GOOGLE_DRIVE_REDIRECT_URI
    )


def _token_cipher():
    key = hashlib.sha256(
        b"agriculture-pos-google-drive-token\0"
        + settings.SECRET_KEY.encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_refresh_token(refresh_token):
    return _token_cipher().encrypt(refresh_token.encode("utf-8")).decode("ascii")


def decrypt_refresh_token(encrypted_token):
    try:
        return _token_cipher().decrypt(encrypted_token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise BackupError(
            "The saved Google Drive connection cannot be decrypted. Reconnect it "
            "after restoring the original Django SECRET_KEY."
        ) from exc


def _read_json_response(request, timeout=30):
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise BackupError(
            f"Google Drive request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise BackupError(f"Google Drive could not be reached: {exc.reason}") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise BackupError("Google returned an invalid response.") from exc


def build_google_authorization_url(state):
    if not google_drive_is_configured():
        raise BackupError(
            "Google Drive is not configured. Add the OAuth client ID and secret "
            "to the private .env file, then restart Django."
        )
    query = urlencode(
        {
            "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_DRIVE_REDIRECT_URI,
            "response_type": "code",
            "scope": (
                "openid email https://www.googleapis.com/auth/drive.file"
            ),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


def exchange_authorization_code(code):
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode(
            {
                "code": code,
                "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
                "client_secret": settings.GOOGLE_DRIVE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_DRIVE_REDIRECT_URI,
                "grant_type": "authorization_code",
            }
        ).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _read_json_response(request)


def google_account_email(access_token):
    request = Request(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    data = _read_json_response(request)
    email = data.get("email")
    if not email or data.get("email_verified") is not True:
        raise BackupError("Google did not confirm the connected account email.")
    return email


def refresh_google_access_token(refresh_token):
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode(
            {
                "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
                "client_secret": settings.GOOGLE_DRIVE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    data = _read_json_response(request)
    access_token = data.get("access_token")
    if not access_token:
        raise BackupError("Google did not return an access token for the backup.")
    return access_token, data.get("refresh_token")


def create_database_backup():
    database = settings.DATABASES["default"]
    if database["ENGINE"] != "django.db.backends.postgresql":
        raise BackupError("Automatic backups require the configured PostgreSQL database.")

    filename = f"agriculture-pos-{timezone.localtime():%Y-%m-%d-%H%M%S}.dump"
    handle = tempfile.NamedTemporaryFile(
        prefix="agriculture-pos-",
        suffix=".dump",
        delete=False,
    )
    backup_path = Path(handle.name)
    handle.close()

    command = [
        "pg_dump",
        "--host",
        str(database.get("HOST") or "localhost"),
        "--port",
        str(database.get("PORT") or "5432"),
        "--username",
        str(database.get("USER") or ""),
        "--dbname",
        str(database["NAME"]),
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(backup_path),
    ]
    process_environment = os.environ.copy()
    if database.get("PASSWORD"):
        process_environment["PGPASSWORD"] = str(database["PASSWORD"])

    try:
        result = subprocess.run(
            command,
            env=process_environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=1800,
        )
    except FileNotFoundError as exc:
        backup_path.unlink(missing_ok=True)
        raise BackupError(
            "pg_dump was not found. Install PostgreSQL command-line tools and "
            "make sure pg_dump is on the Django server's PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        backup_path.unlink(missing_ok=True)
        raise BackupError("The PostgreSQL backup exceeded the 30-minute limit.") from exc

    if result.returncode:
        backup_path.unlink(missing_ok=True)
        detail = (result.stderr or "pg_dump exited unsuccessfully.").strip()
        raise BackupError(detail[-2000:])
    if backup_path.stat().st_size == 0:
        backup_path.unlink(missing_ok=True)
        raise BackupError("pg_dump produced an empty backup file.")
    return backup_path, filename, backup_path.stat().st_size


def upload_backup_to_drive(backup_path, filename, backup_settings):
    refresh_token = decrypt_refresh_token(
        backup_settings.encrypted_refresh_token
    )
    access_token, rotated_refresh_token = refresh_google_access_token(refresh_token)
    if rotated_refresh_token:
        backup_settings.encrypted_refresh_token = encrypt_refresh_token(
            rotated_refresh_token
        )
        backup_settings.save(update_fields=("encrypted_refresh_token", "updated_at"))

    metadata = {"name": filename}
    if backup_settings.drive_folder_id:
        metadata["parents"] = [backup_settings.drive_folder_id]
    request = Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
        data=json.dumps(metadata).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "application/octet-stream",
            "X-Upload-Content-Length": str(backup_path.stat().st_size),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            upload_url = response.headers.get("Location")
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise BackupError(
            f"Google Drive could not start the file upload (HTTP {exc.code}): {detail}"
        ) from exc
    except URLError as exc:
        raise BackupError(f"Google Drive could not be reached: {exc.reason}") from exc
    if not upload_url:
        raise BackupError("Google Drive did not return an upload session.")

    parsed_url = urlsplit(upload_url)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or not parsed_url.hostname.endswith(".googleapis.com")
    ):
        raise BackupError("Google Drive returned an unexpected upload URL.")

    connection = http.client.HTTPSConnection(
        parsed_url.hostname,
        parsed_url.port or 443,
        timeout=1800,
    )
    try:
        with backup_path.open("rb") as backup_file:
            def file_chunks():
                while True:
                    chunk = backup_file.read(1024 * 1024)
                    if not chunk:
                        return
                    yield chunk

            connection.request(
                "PUT",
                parsed_url.path + (f"?{parsed_url.query}" if parsed_url.query else ""),
                body=file_chunks(),
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(backup_path.stat().st_size),
                },
            )
        response = connection.getresponse()
        payload = response.read(4096)
    except OSError as exc:
        raise BackupError(f"The Google Drive upload failed: {exc}") from exc
    finally:
        connection.close()

    if response.status not in (200, 201):
        detail = payload.decode("utf-8", errors="replace")
        raise BackupError(
            f"Google Drive upload failed with HTTP {response.status}: {detail}"
        )
    try:
        return json.loads(payload)["id"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise BackupError("Google Drive did not confirm the uploaded file.") from exc
