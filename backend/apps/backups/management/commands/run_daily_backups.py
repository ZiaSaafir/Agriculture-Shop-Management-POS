from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.organizations.models import Organization

from ...models import BackupRun, OrganizationBackupSettings
from ...services import BackupError, create_database_backup, upload_backup_to_drive


class Command(BaseCommand):
    help = "Create and upload daily PostgreSQL backups for enabled organizations."

    def handle(self, *args, **options):
        configurations = OrganizationBackupSettings.objects.filter(
            daily_enabled=True,
            organization__is_active=True,
        ).select_related("organization")
        if not configurations.exists():
            self.stdout.write("No daily Google Drive backups are enabled.")
            return
        if Organization.objects.count() != 1:
            raise CommandError(
                "Automated backups are limited to the initial single-organization "
                "deployment. Configure a database-wide administrator backup before "
                "enabling backups in a multi-organization installation."
            )

        failures = []
        for config in configurations:
            run = BackupRun.objects.create(
                organization=config.organization,
                status=BackupRun.Status.RUNNING,
                destination="google_drive",
            )
            backup_path = None
            try:
                backup_path, filename, file_size = create_database_backup()
                upload_backup_to_drive(backup_path, filename, config)
                run.status = BackupRun.Status.SUCCEEDED
                run.file_name = filename
                run.file_size = file_size
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Uploaded {filename} for {config.organization.name}."
                    )
                )
            except BackupError as exc:
                run.status = BackupRun.Status.FAILED
                run.error_message = str(exc)
                failures.append(f"{config.organization.name}: {exc}")
                self.stderr.write(
                    self.style.ERROR(
                        f"Backup failed for {config.organization.name}: {exc}"
                    )
                )
            finally:
                if backup_path:
                    Path(backup_path).unlink(missing_ok=True)
                run.completed_at = timezone.now()
                run.save(
                    update_fields=(
                        "status",
                        "file_name",
                        "file_size",
                        "error_message",
                        "completed_at",
                    )
                )
        if failures:
            raise CommandError("; ".join(failures))
