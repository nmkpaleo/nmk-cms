#!/usr/bin/env python
"""Watch incoming uploads and create Media records."""
import os
import time
from pathlib import Path

import django
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from cms.upload_processing import INCOMING, process_file


class UploadHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        process_file(Path(event.src_path))


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
