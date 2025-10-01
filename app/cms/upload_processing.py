import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.utils import timezone as django_timezone

from .models import Media
from . import scanning_utils

logger = logging.getLogger("cms.upload_processing")

INCOMING = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
PENDING = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
REJECTED = Path(settings.MEDIA_ROOT) / "uploads" / "rejected"

NAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\(\d+\)\.png$")

def _fromtimestamp_utc(timestamp: float) -> datetime:
    """Return a UTC-aware datetime built from ``timestamp``."""

    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _select_filesystem_timestamp(stat_result) -> float:
    """Return the best available creation timestamp from ``stat_result``."""

    for attr in ("st_birthtime", "st_mtime", "st_ctime"):
        value = getattr(stat_result, attr, None)
        if value is not None:
            return value
    raise AttributeError("stat_result does not expose a usable timestamp")


def create_media(
    path: Path, *, filesystem_timestamp: float | None = None
) -> None:
    """Create a Media record for a newly accepted scan."""
    if filesystem_timestamp is None:
        filesystem_timestamp = _select_filesystem_timestamp(path.stat())
    filesystem_created = _fromtimestamp_utc(filesystem_timestamp)
    if django_timezone.is_naive(filesystem_created):
        filesystem_created = django_timezone.make_aware(
            filesystem_created, timezone.utc
        )
    logger.info(
        "Processing uploaded media %s with filesystem creation time %s (UTC)",
        path,
        filesystem_created.isoformat(),
    )
    created = scanning_utils.to_nairobi(filesystem_created)
    scanning_utils.auto_complete_scans()
    scan = scanning_utils.find_scan_for_timestamp(created)
    if scan:
        logger.info(
            "Matched media %s to scanning #%s (%s -> %s) using Nairobi timestamp %s",
            path,
            scan.pk,
            scan.start_time,
            scan.end_time,
            created.isoformat(),
        )
    else:
        logger.warning(
            "No scanning found for media %s using Nairobi timestamp %s",
            path,
            created.isoformat(),
        )
    media = Media(
        type="photo",
        license="CC0",
        rights_holder="National Museums of Kenya",
        scanning=scan,
    )
    media.media_location.name = str(path.relative_to(settings.MEDIA_ROOT))
    media.save()


def process_file(src: Path) -> Path:
    """Validate ``src`` and move it to ``pending`` or ``rejected``.

    Returns the destination path after moving. Creates a ``Media`` row for
    valid files.
    """
    if NAME_PATTERN.match(src.name):
        dest = PENDING / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        stat_result = src.stat()
        filesystem_timestamp = _select_filesystem_timestamp(stat_result)
        shutil.move(src, dest)
        create_media(dest, filesystem_timestamp=filesystem_timestamp)
    else:
        dest = REJECTED / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
    return dest
