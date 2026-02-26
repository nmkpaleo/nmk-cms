import os
import shutil
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")

import django

django.setup()

import pytest

pytestmark = pytest.mark.django_db
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from cms.models import Media  # noqa: E402  pylint: disable=wrong-import-position
from cms.upload_processing import process_file  # noqa: E402  pylint: disable=wrong-import-position



@pytest.fixture(autouse=True)
def _current_user_patch(db):
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(
        username="manual-uploader",
        defaults={"is_staff": True, "email": "uploader@example.com"},
    )
    with patch("cms.models.get_current_user", return_value=user):
        yield user


@pytest.fixture(autouse=True)
def _clean_media_storage(db):
    uploads_root = Path(settings.MEDIA_ROOT) / "uploads"
    if uploads_root.exists():
        shutil.rmtree(uploads_root)
    uploads_root.mkdir(parents=True, exist_ok=True)
    Media.objects.all().delete()
    try:
        yield
    finally:
        if uploads_root.exists():
            shutil.rmtree(uploads_root)
        Media.objects.all().delete()


@pytest.fixture(autouse=True)
def _allow_testserver_host():
    original = list(settings.ALLOWED_HOSTS)
    if "testserver" not in original:
        settings.ALLOWED_HOSTS = [*original, "testserver"]
    try:
        yield
    finally:
        settings.ALLOWED_HOSTS = original


@pytest.fixture()
def client():
    return Client()


def test_process_file_accepts_manual_qc_jpeg():
    incoming = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    src = incoming / "1.jpg"
    src.write_bytes(b"jpeg-data")

    dest = process_file(src)

    manual_path = Path(settings.MEDIA_ROOT) / "uploads" / "manual_qc" / "1.jpg"
    assert dest == manual_path
    assert manual_path.exists()

    media = Media.objects.get()
    assert media.media_location == "uploads/manual_qc/1.jpg"
    assert media.file_name == "1.jpg"
    assert media.scanning_id is None


def test_upload_scan_accepts_manual_qc_jpeg(client):
    user_model = get_user_model()
    user = user_model.objects.get(username="manual-uploader")
    user.set_password("pass1234")
    user.is_staff = True
    user.save()

    client.force_login(user)

    upload = SimpleUploadedFile("1.jpg", b"jpeg-data", content_type="image/jpeg")
    response = client.post(reverse("admin-upload-scan"), {"files": [upload]}, follow=True)

    assert response.status_code == 200
    manual_path = Path(settings.MEDIA_ROOT) / "uploads" / "manual_qc" / "1.jpg"
    assert manual_path.exists()

    media = Media.objects.get()
    assert media.media_location == "uploads/manual_qc/1.jpg"
    assert media.file_name == "1.jpg"
    assert media.scanning_id is None
