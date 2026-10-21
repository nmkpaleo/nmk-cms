import time

from django.core.management.base import BaseCommand

from cms.backups import process_next_backup_job


class Command(BaseCommand):
    help = "Process persisted CMS backup and restore jobs."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one queued job and exit.")
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args, **options):
        if options["once"]:
            process_next_backup_job()
            return

        while True:
            if not process_next_backup_job():
                time.sleep(options["poll_interval"])
