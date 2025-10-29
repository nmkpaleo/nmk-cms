import os
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
