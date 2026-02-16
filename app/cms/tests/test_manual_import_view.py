import io
import os
import zipfile
from unittest.mock import patch

import django
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.test.utils import setup_test_environment, teardown_test_environment
from django.urls import reverse

from cms.forms import (
    ManualImportFailure,
    ManualImportSummary,
    ensure_manual_qc_permission,
)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")
django.setup()


def _excel_column_letter(index: int) -> str:
    result = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_minimal_workbook(headers: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    sheet_rows = []
    for row_index, row_values in enumerate([headers, *rows], start=1):
        cells = []
        for column_index, raw_value in enumerate(row_values):
            value = _xml_escape(str(raw_value))
            cell_reference = f"{_excel_column_letter(column_index)}{row_index}"
            cells.append(
                f'<c r="{cell_reference}" t="inlineStr"><is><t>{value}</t></is></c>'
            )
        sheet_rows.append(f"<row r=\"{row_index}\">{''.join(cells)}</row>")

    sheet_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        "<sheetData>"
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )

    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
            "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
            "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
            "<Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
            "</Relationships>",
        )
        zf.writestr(
            "xl/workbook.xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
            "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
            "<sheets><sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>"
            "</Relationships>",
        )
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return buffer.getvalue()


@pytest.fixture(scope="session", autouse=True)
def _migrate_db():
    call_command("migrate", run_syncdb=True, verbosity=0)


@pytest.fixture(scope="session", autouse=True)
def _django_test_environment():
    setup_test_environment()
    try:
        yield
    finally:
        teardown_test_environment()


@pytest.fixture(autouse=True)
def _allow_test_host():
    allowed = list(settings.ALLOWED_HOSTS)
    if "testserver" in allowed or "*" in allowed:
        yield
        return

    settings.ALLOWED_HOSTS = [*allowed, "testserver"]
    try:
        yield
    finally:
        settings.ALLOWED_HOSTS = allowed


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def collection_manager():
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username="manager",
        defaults={
            "email": "manager@example.com",
            "is_staff": True,
        },
    )
    if created:
        user.set_password("password")
        user.save()
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    permission = ensure_manual_qc_permission()
    user.user_permissions.add(permission)
    return user


def test_manual_import_view_requires_permission(client):
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username="viewer",
        defaults={"email": "viewer@example.com", "is_staff": True},
    )
    if created:
        user.set_password("password")
        user.save()
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    client.force_login(user)

    response = client.get(reverse("manual_qc_import"))

    assert response.status_code == 403


def test_manual_import_view_handles_successful_upload(client, collection_manager):
    client.force_login(collection_manager)

    csv_content = b"id,collection_id\n1,KNM\n"
    upload = SimpleUploadedFile("manual.csv", csv_content, content_type="text/csv")

    summary = ManualImportSummary(total_rows=1, success_count=1, created_count=1)

    with patch("cms.forms.run_manual_qc_import", return_value=summary) as mock_run:
        response = client.post(reverse("manual_qc_import"), {"dataset_file": upload})

    assert response.status_code == 200
    assert response.context["result"] == summary

    assert mock_run.called
    args, kwargs = mock_run.call_args
    assert len(args[0]) == 1
    assert kwargs["default_created_by"] == collection_manager.username


def test_manual_import_view_accepts_xlsx_upload(client, collection_manager):
    client.force_login(collection_manager)

    xlsx_content = build_minimal_workbook(["id", "collection_id"], [["1", "KNM"]])
    upload = SimpleUploadedFile(
        "manual.xlsx",
        xlsx_content,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )

    summary = ManualImportSummary(total_rows=1, success_count=1, created_count=1)

    with patch("cms.forms.run_manual_qc_import", return_value=summary) as mock_run:
        response = client.post(reverse("manual_qc_import"), {"dataset_file": upload})

    assert response.status_code == 200
    args, kwargs = mock_run.call_args
    rows = args[0]
    assert len(rows) == 1
    assert rows[0]["id"] == "1"
    assert kwargs["default_created_by"] == collection_manager.username


def test_manual_import_view_generates_error_report(client, collection_manager):
    client.force_login(collection_manager)

    csv_content = b"id,collection_id\n2,KNM\n"
    upload = SimpleUploadedFile("errors.csv", csv_content, content_type="text/csv")

    failure = ManualImportFailure(row_number=2, identifier="2", message="Missing media")
    summary = ManualImportSummary(total_rows=1, failures=[failure])

    with patch("cms.forms.run_manual_qc_import", return_value=summary):
        response = client.post(reverse("manual_qc_import"), {"dataset_file": upload})

    assert response.context["result"].error_count == 1

    download = client.get(reverse("manual_qc_import"), {"download": "errors"})
    assert download.status_code == 200
    assert download["Content-Type"] == "text/csv"
    assert "manual-qc-import-errors.csv" in download["Content-Disposition"]
    assert "Missing media" in download.content.decode("utf-8")
