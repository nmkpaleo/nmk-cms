from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from cms.models import (
    Accession,
    AccessionNumberSeries,
    AccessionRow,
    Identification,
    Taxon,
)


def generate_accessions_from_series(series_user, count, collection, specimen_prefix, creator_user=None):
    try:
        series = AccessionNumberSeries.objects.active_for_user(series_user).get()
    except AccessionNumberSeries.DoesNotExist:
        organisation = getattr(getattr(series_user, "organisation_membership", None), "organisation", None)
        org_display = f" in {organisation}" if organisation else ""
        raise ValueError(
            f"No active accession number series found for user {series_user.username}{org_display}."
        )

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
    return AccessionNumberSeries.objects.active_for_user(user).first()


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


def build_accession_identification_maps(
    rows: Iterable[AccessionRow],
) -> Tuple[Dict[int, Identification], Dict[int, int], Dict[int, Taxon]]:
    """Return cached identification metadata for accession rows.

    The return value contains three dictionaries keyed by accession row ID and
    identification ID respectively:

    ``first_identifications``
        Maps each row ID to its most recent identification (if any).

    ``identification_counts``
        Maps each row ID to the total number of related identifications.

    ``taxonomy_map``
        Maps the identification ID for the first identification to a resolved
        :class:`Taxon` instance. The taxon is sourced from the
        ``taxon_record`` relation when present and falls back to a batched
        lookup on ``taxon`` values when that relation is absent.
    """

    first_identifications: Dict[int, Identification] = {}
    identification_counts: Dict[int, int] = {}
    taxonomy_map: Dict[int, Taxon] = {}
    pending_taxa: Dict[int, str] = {}

    for row in rows:
        identifications = list(row.identification_set.all())
        if not identifications:
            continue

        first_identification = identifications[0]
        first_identifications[row.id] = first_identification
        identification_counts[row.id] = len(identifications)

        taxon_record = first_identification.taxon_record
        if taxon_record is not None:
            taxonomy_map[first_identification.id] = taxon_record
            continue

        taxon_name = (first_identification.taxon or "").strip()
        if taxon_name:
            pending_taxa[first_identification.id] = taxon_name

    if pending_taxa:
        query = Q()
        seen_names = set()
        for name in pending_taxa.values():
            lowered = name.lower()
            if lowered in seen_names:
                continue
            seen_names.add(lowered)
            query |= Q(taxon_name__iexact=name)

        if query:
            matched_taxa = Taxon.objects.filter(query)
            taxonomy_lookup: Dict[str, Taxon] = {}
            for taxon in matched_taxa:
                taxonomy_lookup.setdefault(taxon.taxon_name.lower(), taxon)

            for identification_id, taxon_name in pending_taxa.items():
                match = taxonomy_lookup.get(taxon_name.lower())
                if match is not None:
                    taxonomy_map[identification_id] = match

    return first_identifications, identification_counts, taxonomy_map
