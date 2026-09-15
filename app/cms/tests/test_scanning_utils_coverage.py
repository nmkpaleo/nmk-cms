from datetime import timedelta

import pytest
from crum import set_current_user
from django.utils import timezone

from cms.models import DrawerRegister, Scanning
from cms.scanning_utils import (
    auto_complete_scans,
    calculate_scan_auto_end,
    find_scan_for_timestamp,
    to_nairobi,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def scan_user(django_user_model):
    user = django_user_model.objects.create_user(username="scanner", password="x")
    set_current_user(user)
    return user


@pytest.fixture(autouse=True)
def cleanup_current_user():
    try:
        yield
    finally:
        set_current_user(None)


def _create_drawer(user):
    set_current_user(user)
    return DrawerRegister.objects.create(code="ABC", description="drawer", estimated_documents=10)


def test_to_nairobi_returns_none_for_none_input():
    assert to_nairobi(None) is None


def test_calculate_scan_auto_end_caps_to_eight_hours_or_midnight():
    start = timezone.datetime(2024, 1, 1, 10, 0, tzinfo=timezone.get_current_timezone())
    end = calculate_scan_auto_end(start)
    assert end >= to_nairobi(start)
    assert (end - to_nairobi(start)) <= timedelta(hours=8)


def test_auto_complete_scans_sets_end_time_when_expired(scan_user):
    drawer = _create_drawer(scan_user)
    start = timezone.now() - timedelta(hours=10)
    set_current_user(scan_user)
    scan = Scanning.objects.create(drawer=drawer, user=scan_user, start_time=start)

    auto_complete_scans([scan])
    scan.refresh_from_db()

    assert scan.end_time is not None


def test_find_scan_for_timestamp_returns_matching_open_scan(scan_user):
    drawer = _create_drawer(scan_user)
    start = timezone.now() - timedelta(hours=1)
    set_current_user(scan_user)
    scan = Scanning.objects.create(drawer=drawer, user=scan_user, start_time=start, end_time=None)

    found = find_scan_for_timestamp(timezone.now())
    assert found is not None
    assert found.id == scan.id
