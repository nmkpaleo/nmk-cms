#!/usr/bin/env python
"""Watch incoming uploads and create Media records."""
import logging
import os
import time
from pathlib import Path

import django
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from cms.upload_processing import INCOMING, find_uploaded_scans, process_file, scan_upload_lock

logger = logging.getLogger(__name__)


class UploadHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        with scan_upload_lock():
            path = Path(event.src_path)
            if not path.is_file():
                return
            existing = find_uploaded_scans([path.name], exclude_path=path)
            if path.name in existing:
                logger.info(
                    "Already uploaded %s (%s); leaving incoming duplicate at %s",
                    path.name, existing[path.name] or "folder not recorded", path,
                )
                return
            process_file(path)


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
