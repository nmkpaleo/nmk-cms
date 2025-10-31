from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from cms.models import Accession, AccessionNumberSeries

def generate_accessions_from_series(series_user, count, collection, specimen_prefix, creator_user=None):
    try:
        series = AccessionNumberSeries.objects.get(user=series_user, is_active=True)
    except AccessionNumberSeries.DoesNotExist:
        raise ValueError(f"No active accession number series found for user {series_user.username}.")

    start = series.current_number
    end = start + count - 1

    if end > series.end_at:
        raise ValueError("Not enough accession numbers left in this series.")

    accessions = []
    for number in range(start, end + 1):
        accessions.append(Accession(
            collection=collection,
            specimen_prefix=specimen_prefix,
            specimen_no=number,
            accessioned_by=series_user,
            instance_number=1,
            created_by=creator_user,
            modified_by=creator_user
        ))

    # ✅ Only update current_number if everything is valid
    series.current_number = end + 1
    series.save()

    # ✅ Save accessions individually to trigger signals
    for acc in accessions:
        acc.save()

    return accessions

def get_active_series_for_user(user):
    return AccessionNumberSeries.objects.filter(user=user, is_active=True).first()


def build_history_entries(instance):
    """Return structured change history entries for a model instance.

    Each entry contains the historical log record and a list of field-level
    changes with verbose field names and resolved foreign-key references.
    """
    model = type(instance)
    history_entries = []
    for log in instance.history.all().order_by("-history_date", "-history_id"):
        prev = log.prev_record
        changes = []
        if prev:
            delta = log.diff_against(prev)
            for change in delta.changes:
                field = model._meta.get_field(change.field)
                field_name = field.verbose_name.capitalize()
                old = change.old
                new = change.new
                if isinstance(field, models.ForeignKey):
                    related_model = field.remote_field.model
                    old_obj = related_model.objects.filter(pk=old).first()
                    new_obj = related_model.objects.filter(pk=new).first()
                    old = str(old_obj) if old_obj else old
                    new = str(new_obj) if new_obj else new
                elif isinstance(field, models.ManyToManyField):
                    related_model = field.remote_field.model
                    old_ids = set(old or [])
                    new_ids = set(new or [])
                    old_objs = related_model.objects.filter(pk__in=old_ids)
                    new_objs = related_model.objects.filter(pk__in=new_ids)
                    old = ", ".join(str(obj) for obj in old_objs)
                    new = ", ".join(str(obj) for obj in new_objs)
                changes.append({"field": field_name, "old": old, "new": new})
        history_entries.append({"log": log, "changes": changes})
    return history_entries


def coerce_stripped(value: Any | None) -> str | None:
    """Return ``value`` as a stripped string or ``None`` if empty."""

    if value in (None, ""):
        return None
    if isinstance(value, str):
        result = value.strip()
        if result == "\\N":
            return None
        return result or None
    result = str(value).strip()
    if result == "\\N":
        return None
    return result or None


def normalise_yes_no(value: Any | None) -> bool:
    """Interpret common truthy strings (yes/true/1) as ``True``."""

    if value in (None, ""):
        return False
    return str(value).strip().lower() in {"yes", "true", "1", "y", "t"}

