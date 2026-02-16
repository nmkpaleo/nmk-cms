"""Management command for importing manually curated QC data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cms.forms import (
    dataset_to_rows,
    ensure_manual_qc_permission,
    load_manual_qc_dataset,
    run_manual_qc_import,
)
from cms.models import Media


class Command(BaseCommand):
    help = "Import manually validated QC spreadsheet data and create accessions."

    def add_arguments(self, parser) -> None:  # pragma: no cover - argparse plumbing
        parser.add_argument(
            "path",
            type=str,
            help="Path to the manual QC spreadsheet (CSV or Excel).",
        )
        parser.add_argument(
            "--username",
            required=True,
            help="Username executing the import (must have cms.can_import_manual_qc).",
        )
        parser.add_argument(
            "--error-report",
            dest="error_report",
            help="Optional path to write a CSV error report for failed rows.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        username: str = options["username"]
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=username)
        except user_model.DoesNotExist as exc:  # type: ignore[attr-defined]
            raise CommandError(f"User '{username}' does not exist") from exc

        permission = ensure_manual_qc_permission()
        permission_string = f"{permission.content_type.app_label}.{permission.codename}"
        if not (user.is_superuser or user.has_perm(permission_string)):
            raise CommandError(
                "User lacks the cms.can_import_manual_qc permission required to import manual QC data."
            )

        try:
            with path.open("rb") as handle:
                dataset = load_manual_qc_dataset(handle)
                rows = dataset_to_rows(dataset)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        summary = run_manual_qc_import(
            rows,
            queryset=Media.objects.all(),
            default_created_by=user.get_username(),
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Processed %(total)d rows; %(success)d succeeded; %(errors)d failed." % {
                    "total": summary.total_rows,
                    "success": summary.success_count,
                    "errors": summary.error_count,
                }
            )
        )

        if summary.created_count:
            self.stdout.write(
                "Created %(count)d accession records from the import." % {
                    "count": summary.created_count,
                }
            )

        if summary.error_count:
            self.stdout.write(
                self.style.WARNING(
                    "%(count)d rows failed during import." % {"count": summary.error_count}
                )
            )
            report_path_value = options.get("error_report")
            if report_path_value:
                report_path = Path(report_path_value)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(summary.build_error_report(), encoding="utf-8")
                self.stdout.write(f"Error report written to {report_path}")
            else:
                for failure in summary.failures[:10]:
                    identifier = failure.identifier or "n/a"
                    self.stdout.write(
                        f"Row {failure.row_number} ({identifier}): {failure.message}"
                    )
                if summary.error_count > 10:
                    remaining = summary.error_count - 10
                    self.stdout.write(f"... {remaining} additional errors not shown.")

