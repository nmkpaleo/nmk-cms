from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
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
    root.mkdir(parents=True, exist_ok=True)
    return root


def list_backup_files() -> list[BackupFile]:
    files = []
    root = backup_root()
    for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        if path.name.startswith(DATABASE_PREFIX) and path.suffix == ".sql":
            kind = "database"
        elif path.name.startswith(FILES_PREFIX) and path.name.endswith(".tar.gz"):
            kind = "files"
        else:
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
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path


def create_backup_set() -> BackupSet:
    timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    root = backup_root()
    database_path = root / f"{DATABASE_PREFIX}_{timestamp}.sql"
    files_path = root / f"{FILES_PREFIX}_{timestamp}.tar.gz"

    dump_database(database_path)
    archive_media(files_path)
    _lock_down(database_path)
    _lock_down(files_path)
    return BackupSet(timestamp=timestamp, database_path=database_path, files_path=files_path)


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
