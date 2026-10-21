from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.utils import timezone


DATABASE_PREFIX = "paleocms_database"
FILES_PREFIX = "paleocms_files"


@dataclass(frozen=True)
class BackupFile:
    name: str
    size: int
    modified_at: object
    kind: str


@dataclass(frozen=True)
class BackupSet:
    timestamp: str
    database_path: Path
    files_path: Path


def backup_root() -> Path:
    root = Path(settings.CMS_BACKUP_ROOT).expanduser()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def list_backup_files() -> list[BackupFile]:
    files = []
    root = backup_root()
    published_sets = {
        path.name.removeprefix("paleocms_backup_").removesuffix(".complete")
        for path in root.glob("paleocms_backup_*.complete")
        if path.is_file()
    }
    for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        if path.name.startswith(DATABASE_PREFIX) and path.suffix == ".sql":
            kind = "database"
        elif path.name.startswith(FILES_PREFIX) and path.name.endswith(".tar.gz"):
            kind = "files"
        else:
            continue
        timestamp = path.name.removeprefix(f"{DATABASE_PREFIX}_").removesuffix(".sql")
        if kind == "files":
            timestamp = path.name.removeprefix(f"{FILES_PREFIX}_").removesuffix(".tar.gz")
        if timestamp not in published_sets:
            continue
        stat = path.stat()
        files.append(
            BackupFile(
                name=path.name,
                size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
                kind=kind,
            )
        )
    return files


def resolve_backup_file(filename: str) -> Path:
    root = backup_root().resolve()
    path = (root / filename).resolve()
    if root not in (path, *path.parents):
        raise SuspiciousFileOperation("Backup path is outside the configured backup directory.")
    if path.parent != root or not path.is_file():
        raise FileNotFoundError(filename)
    if not any(item.name == path.name for item in list_backup_files()):
        raise FileNotFoundError(filename)
    return path


def create_backup_set() -> BackupSet:
    timestamp = f"{timezone.localtime():%Y%m%d_%H%M%S}_{uuid.uuid4().hex}"
    root = backup_root()
    database_path = root / f"{DATABASE_PREFIX}_{timestamp}.sql"
    files_path = root / f"{FILES_PREFIX}_{timestamp}.tar.gz"
    marker_path = root / f"paleocms_backup_{timestamp}.complete"

    with tempfile.TemporaryDirectory(prefix=".backup-", dir=root) as staging_directory:
        staging = Path(staging_directory)
        staged_database = staging / database_path.name
        staged_files = staging / files_path.name
        try:
            dump_database(staged_database)
            archive_media(staged_files)
            _lock_down(staged_database)
            _lock_down(staged_files)
            os.replace(staged_database, database_path)
            os.replace(staged_files, files_path)
            staged_marker = staging / marker_path.name
            staged_marker.touch(mode=0o600)
            os.replace(staged_marker, marker_path)
        except Exception:
            database_path.unlink(missing_ok=True)
            files_path.unlink(missing_ok=True)
            marker_path.unlink(missing_ok=True)
            raise
    return BackupSet(timestamp=timestamp, database_path=database_path, files_path=files_path)


def queue_backup_job(operation: str, *, user=None, uploaded_file=None):
    from .models import CMSBackupJob

    if operation not in CMSBackupJob.Operation.values:
        raise ValueError(f"Unsupported backup operation: {operation}")

    source_path = ""
    if uploaded_file is not None:
        suffix = ".sql" if operation == CMSBackupJob.Operation.RESTORE_DATABASE else ".tar.gz"
        descriptor, filename = tempfile.mkstemp(prefix="restore-", suffix=suffix, dir=backup_root())
        source_path = filename
        try:
            with os.fdopen(descriptor, "wb") as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            Path(source_path).chmod(0o600)
            return CMSBackupJob.objects.create(
                operation=operation,
                source_path=source_path,
                created_by=user,
            )
        except Exception:
            Path(source_path).unlink(missing_ok=True)
            raise
    return CMSBackupJob.objects.create(operation=operation, created_by=user)


def process_next_backup_job() -> bool:
    from django.db import transaction
    from django.utils import timezone

    from .models import CMSBackupJob

    with transaction.atomic():
        job = (
            CMSBackupJob.objects.select_for_update()
            .filter(status=CMSBackupJob.Status.QUEUED)
            .order_by("created_at", "pk")
            .first()
        )
        if job is None:
            return False
        job.status = CMSBackupJob.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

    result = ""
    error = ""
    status = CMSBackupJob.Status.SUCCEEDED
    try:
        if job.operation == CMSBackupJob.Operation.CREATE:
            backup_set = create_backup_set()
            result = f"{backup_set.database_path.name}, {backup_set.files_path.name}"
        elif job.operation == CMSBackupJob.Operation.RESTORE_DATABASE:
            restore_database(Path(job.source_path))
            result = "Database restore completed."
        elif job.operation == CMSBackupJob.Operation.RESTORE_FILES:
            restore_media(Path(job.source_path))
            result = "Media restore completed."
    except Exception as exc:
        status = CMSBackupJob.Status.FAILED
        error = str(exc)
    finally:
        if job.source_path:
            Path(job.source_path).unlink(missing_ok=True)
        finished_at = timezone.now()
        created_by_id = None if job.operation == CMSBackupJob.Operation.RESTORE_DATABASE else job.created_by_id
        CMSBackupJob.objects.update_or_create(
            pk=job.pk,
            defaults={
                "operation": job.operation,
                "status": status,
                "source_path": "",
                "result": result,
                "error": error,
                "created_by_id": created_by_id,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": finished_at,
            },
        )
    return True


def dump_database(output_path: Path) -> None:
    database = settings.DATABASES["default"]
    engine = database.get("ENGINE", "")
    if "mysql" not in engine:
        raise ImproperlyConfigured("CMS backup currently supports MySQL/MariaDB databases.")

    executable = _first_available("mariadb-dump", "mysqldump")
    command = [
        executable,
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--default-character-set=utf8mb4",
        f"--ignore-table={database.get('NAME')}.cms_cmsbackupjob",
        f"--host={database.get('HOST') or 'localhost'}",
        f"--user={database.get('USER')}",
    ]
    if database.get("PORT"):
        command.append(f"--port={database.get('PORT')}")
    command.append(database.get("NAME"))

    with output_path.open("wb") as output:
        subprocess.run(command, stdout=output, stderr=subprocess.PIPE, env=_mysql_env(database), check=True)


def restore_database(sql_path: Path) -> None:
    database = settings.DATABASES["default"]
    engine = database.get("ENGINE", "")
    if "mysql" not in engine:
        raise ImproperlyConfigured("CMS restore currently supports MySQL/MariaDB databases.")

    executable = _first_available("mariadb", "mysql")
    command = [
        executable,
        "--binary-mode",
        f"--host={database.get('HOST') or 'localhost'}",
        f"--user={database.get('USER')}",
    ]
    if database.get("PORT"):
        command.append(f"--port={database.get('PORT')}")
    command.append(database.get("NAME"))

    with sql_path.open("rb") as sql_file:
        subprocess.run(command, stdin=sql_file, stderr=subprocess.PIPE, env=_mysql_env(database), check=True)


def archive_media(output_path: Path) -> None:
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz") as archive:
        for item in sorted(media_root.iterdir()):
            archive.add(item, arcname=item.name, recursive=True)


def restore_media(archive_path: Path) -> None:
    destination = Path(settings.MEDIA_ROOT)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        _safe_extract(archive, destination)


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.getmembers():
        if member.issym() or member.islnk():
            raise SuspiciousFileOperation("Archive links are not allowed in media restores.")
        member_path = (destination / member.name).resolve()
        if destination not in (member_path, *member_path.parents):
            raise SuspiciousFileOperation("Archive contains a path outside the media directory.")
    archive.extractall(destination)


def _first_available(*names: str) -> str:
    for name in names:
        executable = shutil.which(name)
        if executable:
            return executable
    raise ImproperlyConfigured(f"Install one of these database clients: {', '.join(names)}.")


def _mysql_env(database: dict) -> dict[str, str]:
    env = os.environ.copy()
    password = database.get("PASSWORD")
    if password:
        env["MYSQL_PWD"] = str(password)
    return env


def _lock_down(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass
