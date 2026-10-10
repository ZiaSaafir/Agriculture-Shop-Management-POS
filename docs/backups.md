# PostgreSQL backups

The administrator-only Settings workspace supports:

- Manual PostgreSQL custom-format (`.dump`) downloads. In the browser's download
  settings, enable **Ask where to save each file** to save directly to a USB
  drive. This is a whole-database backup and should be stored securely.
- One connected Google account per organization, authorized using Google OAuth.
  The app stores the refresh token encrypted with a key derived from Django's
  `SECRET_KEY`; the token is not returned by the API. Preserve the original
  `SECRET_KEY` in a separate, secure location. Rotating it requires reconnecting
  Google Drive.
- Daily Drive uploads by the `run_daily_backups` Django management command.
  Enabling daily uploads in Settings does not create an operating-system
  schedule by itself; Windows Task Scheduler must run the command each day.
- Backup run history and explicit failure details in Settings.

## Google Drive setup

1. Create a Google Cloud project, enable the Google Drive API, and create an
   OAuth client ID for a **Web application**.
2. Add this exact authorized redirect URI for the local installation:

   ```text
   http://127.0.0.1:8000/api/backups/google/callback/
   ```

3. Put `GOOGLE_DRIVE_CLIENT_ID` and `GOOGLE_DRIVE_CLIENT_SECRET` in the private
   project `.env` file. Do not commit either value. Restart Django.
4. Sign in as a shop administrator and open **Settings**. Choose **Connect
   Google Drive**, sign in to the single Google account that should receive
   backups, and approve the requested Drive file access.
5. Optionally provide a Drive folder ID, enable daily uploads, and save.

OAuth scope is limited to the `drive.file` scope plus verified account email.
The app creates backup files through its own Drive integration; it does not
receive general access to every file in the connected account.
If the OAuth consent screen is left in Google's testing mode, refresh tokens can
expire; use a suitable production/internal consent configuration for a
continuously running daily backup.

## Schedule the daily upload on Windows

Create a task in **Task Scheduler** on the computer that hosts Django and
PostgreSQL:

1. Choose **Create Task** and set the task to run daily at a time when the
   computer and PostgreSQL service are normally available.
2. Use the Windows account that can read the project `.env`, run the project
   Python environment, and reach PostgreSQL. To run while signed out, select
   **Run whether user is logged on or not** and save that account's Windows
   credentials in Task Scheduler.
3. Add a **Start a program** action. Set **Program/script** to the absolute
   path to `.venv\Scripts\python.exe`.
4. Set **Add arguments** to the absolute path to `backend\manage.py`, followed
   by `run_daily_backups`; for example:

   ```text
   "C:\AgriculturePos\backend\manage.py" run_daily_backups
   ```

5. Set **Start in** to the project root, for example `C:\AgriculturePos`.
6. Use **Run** in Task Scheduler once, then check **Settings → Backup history**
   and the task's **Last Run Result**.

The management command does not require the Django web server to be running,
but the database, network, Google OAuth configuration, and `pg_dump` executable
must be available. Install the PostgreSQL command-line tools and make sure
`pg_dump` is on the task account's `PATH`. A failed upload is recorded and
returns a non-zero task result. Backups are retained in Drive; this version
does not automatically delete older files.

## Restore and safety

The `.dump` file is PostgreSQL's compressed custom archive format. Restore into
a new, empty test database first with PostgreSQL's `pg_restore` tools and verify
the application before planning a production restore. A database backup may
contain all shop records, so restrict access to the Google account and USB
media. Backups are not encrypted by the application itself.

Backups currently cover the whole PostgreSQL database. To avoid exposing another
shop's data, shop administrators can create/download backups only while this
installation has one organization. A system superuser can make a whole-database
backup if more than one organization is present. Per-organization exports and
restore workflows are not implemented.
