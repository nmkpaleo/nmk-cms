#!/usr/bin/env python
"""Watch incoming uploads and create Media records."""
import os
import re
import shutil
import time
from pathlib import Path

import django
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from cms.models import Media, Scanning

INCOMING = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
PENDING = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
REJECTED = Path(settings.MEDIA_ROOT) / "uploads" / "rejected"

for folder in [INCOMING, PENDING, REJECTED]:
    folder.mkdir(parents=True, exist_ok=True)

NAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\(\d+\)\.png$")


def create_media(path: Path) -> None:
    """Create a Media record for the given file."""
    file_date = path.name[:10]
    scan = (
        Scanning.objects.filter(
            start_time__date__lte=file_date,
            end_time__date__gte=file_date,
        )
        .first()
    )

    media = Media(
        type="photo",
        license="CC0",
        rights_holder="National Museums of Kenya",
        scanning=scan,
    )
    media.media_location.name = str(path.relative_to(settings.MEDIA_ROOT))
    media.save()


class UploadHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        src = Path(event.src_path)
        if NAME_PATTERN.match(src.name):
            dest = PENDING / src.name
            shutil.move(src, dest)
            create_media(dest)
        else:
            dest = REJECTED / src.name
            shutil.move(src, dest)


def main():
    handler = UploadHandler()
    observer = Observer()
    observer.schedule(handler, str(INCOMING), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
