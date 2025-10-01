import re
import shutil
from pathlib import Path
from datetime import datetime

from django.conf import settings

from .models import Media
from . import scanning_utils

INCOMING = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
PENDING = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
REJECTED = Path(settings.MEDIA_ROOT) / "uploads" / "rejected"

NAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\(\d+\)\.png$")


def create_media(path: Path) -> None:
    """Create a Media record for a newly accepted scan."""
    created = datetime.fromtimestamp(path.stat().st_ctime)
    created = scanning_utils.to_nairobi(created)
    scanning_utils.auto_complete_scans()
    scan = scanning_utils.find_scan_for_timestamp(created)
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
        shutil.move(src, dest)
        create_media(dest)
    else:
        dest = REJECTED / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
    return dest
