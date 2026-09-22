from datetime import date

from django.core.management.base import BaseCommand, CommandError

from cms.openai_billing import BillingSyncError, sync_costs


class Command(BaseCommand):
    help = "Synchronize OpenAI organization costs and refresh credit estimates (schedule hourly)."

    def add_arguments(self, parser):
        parser.add_argument("--since", type=date.fromisoformat, help="Backfill from this UTC date (YYYY-MM-DD).")

    def handle(self, *args, **options):
        try:
            state = sync_costs(start_date=options["since"])
        except BillingSyncError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS(f"OpenAI costs synchronized through {state.costs_through.isoformat()}."))
