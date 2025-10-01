"""Utility helpers for managing scanning tasks and timestamps."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from django.utils import timezone


NAIROBI_TZ = ZoneInfo("Africa/Nairobi")


def nairobi_now() -> datetime:
    """Return the current time in the Africa/Nairobi timezone."""

    return timezone.now().astimezone(NAIROBI_TZ)


def to_nairobi(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert ``dt`` to the Africa/Nairobi timezone."""

    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, NAIROBI_TZ)
    return dt.astimezone(NAIROBI_TZ)


def calculate_scan_auto_end(start_time: datetime) -> datetime:
    """Return the automatic end timestamp for a scan.

    A scanning task ends automatically after eight hours or at midnight,
    whichever comes first, using the Africa/Nairobi timezone.
    """

    start_nairobi = to_nairobi(start_time)
    assert start_nairobi is not None
    end_of_day = start_nairobi.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    eight_hours_later = start_nairobi + timedelta(hours=8)
    return min(eight_hours_later, end_of_day)


def auto_complete_scans(scans: Optional[Iterable["Scanning"]] = None) -> None:
    """Persist automatic end times for any expired scanning tasks."""

    from .models import Scanning

    queryset: Iterable[Scanning]
    if scans is None:
        queryset = Scanning.objects.filter(end_time__isnull=True)
    else:
        queryset = scans

    current_time = nairobi_now()
    for scan in queryset:
        if scan.end_time:
            continue
        auto_end = calculate_scan_auto_end(scan.start_time)
        if current_time >= auto_end:
            scan.end_time = auto_end
            scan.save(update_fields=["end_time"])


def find_scan_for_timestamp(timestamp: datetime):
    """Return the scan covering ``timestamp`` based on Nairobi time."""

    from .models import Scanning

    created = to_nairobi(timestamp)
    assert created is not None
    scan = (
        Scanning.objects.filter(start_time__lte=created, end_time__gte=created)
        .order_by("-start_time")
        .first()
    )
    if scan:
        return scan

    open_scans = (
        Scanning.objects.filter(start_time__lte=created, end_time__isnull=True)
        .order_by("-start_time")
    )
    for candidate in open_scans:
        if calculate_scan_auto_end(candidate.start_time) >= created:
            return candidate
    return None

