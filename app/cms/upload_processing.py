import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings

from .models import Media
from . import scanning_utils

logger = logging.getLogger("cms.upload_processing")

INCOMING = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
PENDING = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
REJECTED = Path(settings.MEDIA_ROOT) / "uploads" / "rejected"

TIMESTAMP_FORMAT = "%Y-%m-%dT%H%M%S"
NAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}\.png$")


def create_media(
    path: Path, *, scan_timestamp: datetime
) -> None:
    """Create a Media record for a newly accepted scan."""
    logger.info(
        "Processing uploaded media %s with filename timestamp %s",
        path,
        scan_timestamp.isoformat(),
    )
    created = scanning_utils.to_nairobi(scan_timestamp)
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
        timestamp = datetime.strptime(src.stem, TIMESTAMP_FORMAT)
        timestamp = timestamp.replace(tzinfo=scanning_utils.NAIROBI_TZ)
        shutil.move(src, dest)
        create_media(dest, scan_timestamp=timestamp)
    else:
        dest = REJECTED / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
    return dest
