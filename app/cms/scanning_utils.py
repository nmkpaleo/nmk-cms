"""Utilities for normalising scanning-related timestamps."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone as django_timezone

NAIROBI_TZ = ZoneInfo("Africa/Nairobi")


def to_nairobi(value: datetime) -> datetime:
    """Return ``value`` converted to the Africa/Nairobi timezone.

    Naive datetimes are assumed to represent UTC instants, matching how
    filesystem timestamps are stored. The result is always timezone-aware.
    """

    if django_timezone.is_naive(value):
        value = value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(NAIROBI_TZ)


__all__ = ["NAIROBI_TZ", "to_nairobi"]

