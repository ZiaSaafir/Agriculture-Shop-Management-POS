from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase, override_settings

from .services import (
    BackupError,
    build_google_authorization_url,
    create_database_backup,
    decrypt_refresh_token,
    encrypt_refresh_token,
)


class BackupServiceTests(SimpleTestCase):
    @override_settings(SECRET_KEY="test-secret-key")
    def test_refresh_token_is_encrypted_and_round_trips(self):
        encrypted = encrypt_refresh_token("refresh-token-value")

        self.assertNotEqual(encrypted, "refresh-token-value")
        self.assertEqual(decrypt_refresh_token(encrypted), "refresh-token-value")

    @override_settings(SECRET_KEY="first-secret-key")
    def test_changing_django_secret_key_requires_drive_reconnection(self):
        encrypted = encrypt_refresh_token("refresh-token-value")
        with override_settings(SECRET_KEY="second-secret-key"):
            with self.assertRaises(BackupError):
                decrypt_refresh_token(encrypted)

    @override_settings(
        GOOGLE_DRIVE_CLIENT_ID="oauth-client-id",
        GOOGLE_DRIVE_CLIENT_SECRET="oauth-client-secret",
        GOOGLE_DRIVE_REDIRECT_URI=(
            "http://127.0.0.1:8000/api/backups/google/callback/"
        ),
    )
    def test_google_authorization_requests_offline_drive_file_access(self):
        url = build_google_authorization_url("signed-state")
        query = parse_qs(urlsplit(url).query)

        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["state"], ["signed-state"])
        self.assertIn("drive.file", query["scope"][0])
        self.assertNotIn("drive", query["scope"][0].replace("drive.file", ""))

    @override_settings(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}}
    )
    def test_backup_rejects_non_postgresql_database(self):
        with self.assertRaisesMessage(
            BackupError,
            "Automatic backups require the configured PostgreSQL database.",
        ):
            create_database_backup()
