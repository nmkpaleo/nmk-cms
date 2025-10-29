"""Utilities for importing manually curated QC rows into accession records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext_lazy as _

from .models import Media
from .ocr_processing import create_accessions_from_media, make_interpreted_value
from .utils import coerce_stripped, normalise_yes_no


class ManualImportError(Exception):
    """Raised when a manual QC import row cannot be processed."""


@dataclass(slots=True)
class ManualRowContext:
    collection_abbreviation: str | None
    specimen_prefix: str | None
    specimen_number: int | None
    specimen_suffix: str | None


ACCESSION_RE = re.compile(
    r"^(?:(?P<collection>[A-Za-z]+)\s*[-:]\s*)?(?P<prefix>[A-Za-z]+)?[\s-]*(?P<number>\d+)(?:[\s\-/]*(?P<suffix>[A-Za-z0-9]+))?",
    flags=re.IGNORECASE,
)


def parse_accession_number(accession_number: Any) -> ManualRowContext:
    value = coerce_stripped(accession_number)
    if not value:
        return ManualRowContext(None, None, None, None)

    match = ACCESSION_RE.match(value)
    if not match:
        return ManualRowContext(None, None, None, None)

    number_str = match.group("number")
    try:
        number = int(number_str)
    except (TypeError, ValueError):
        number = None

    suffix = coerce_stripped(match.group("suffix"))
    if suffix:
        suffix = suffix.upper()

    prefix = coerce_stripped(match.group("prefix"))
    if prefix:
        prefix = prefix.upper()

    collection = coerce_stripped(match.group("collection"))
    if collection:
        collection = collection.upper()

    return ManualRowContext(collection, prefix, number, suffix)


def make_taxon_value(row: Mapping[str, Any]) -> str | None:
    pieces: list[str] = []
    for key in ("taxon", "family", "subfamily", "tribe", "genus", "species"):
        value = coerce_stripped(row.get(key))
        if value:
            pieces.append(value)
    if not pieces:
        return None
    return " | ".join(dict.fromkeys(pieces))


def parse_coordinates(value: Any) -> tuple[str | None, str | None]:
    text = coerce_stripped(value)
    if not text:
        return None, None
    matches = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if len(matches) >= 2:
        return matches[0], matches[1]
    return text, None


def parse_body_parts(value: Any) -> list[str]:
    text = coerce_stripped(value)
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"[;,]\s*", text) if part.strip()]
    return parts or [text]


def parse_fragments(value: Any) -> str | None:
    text = coerce_stripped(value)
    return text


def build_reference_entries(value: Any) -> list[dict[str, dict[str, Any]]]:
    text = coerce_stripped(value)
    if not text:
        return []

    year_match = re.search(r"(18|19|20)\d{2}", text)
    page_match = re.search(r"p(?:p\.)?\.?\s*(?P<page>[\d\-–, ]+)", text, flags=re.IGNORECASE)

    first_author = text.split(",", 1)[0].strip()
    interpreted_title = text
    year = year_match.group(0) if year_match else None
    page = page_match.group("page").strip() if page_match else None

    entry = {
        "reference_first_author": make_interpreted_value(first_author),
        "reference_title": make_interpreted_value(interpreted_title),
        "reference_year": make_interpreted_value(year),
    }
    if page:
        entry["page"] = make_interpreted_value(page)
    return [entry]


def build_field_slip(row: Mapping[str, Any], taxon_value: str | None) -> dict[str, Any]:
    locality_parts = [coerce_stripped(row.get("locality")), coerce_stripped(row.get("site_area"))]
    verbatim_locality = " | ".join([part for part in locality_parts if part]) or None
    formation = coerce_stripped(row.get("formation"))
    member = coerce_stripped(row.get("member_horizon_level"))

    latitude, longitude = parse_coordinates(row.get("coordinates"))

    slip: dict[str, Any] = {
        "field_number": make_interpreted_value(
            coerce_stripped(row.get("field_number_printed"))
            or coerce_stripped(row.get("field_number"))
        ),
        "collection_date": make_interpreted_value(coerce_stripped(row.get("date"))),
        "verbatim_locality": make_interpreted_value(verbatim_locality),
        "verbatim_taxon": make_interpreted_value(taxon_value),
        "verbatim_element": make_interpreted_value(coerce_stripped(row.get("body_parts"))),
        "aerial_photo": make_interpreted_value(coerce_stripped(row.get("photo_id"))),
        "verbatim_latitude": make_interpreted_value(latitude),
        "verbatim_longitude": make_interpreted_value(longitude),
    }

    horizon: dict[str, Any] = {}
    if formation:
        horizon["formation"] = make_interpreted_value(formation)
    if member:
        horizon["member"] = make_interpreted_value(member)
    if horizon:
        slip["verbatim_horizon"] = horizon

    return slip


def build_row_section(
    context: ManualRowContext,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    storage = make_interpreted_value(coerce_stripped(row.get("shelf")))
    body_parts = parse_body_parts(row.get("body_parts"))
    fragments = parse_fragments(row.get("fragments"))

    natures: list[dict[str, Any]] = []
    for part in body_parts or [None]:
        element_value = coerce_stripped(part)
        nature_entry = {
            "verbatim_element": make_interpreted_value(element_value),
        }
        side_match = None
        if element_value:
            if re.search(r"\b(rt\.?|right)\b", element_value, flags=re.IGNORECASE):
                side_match = "Right"
            elif re.search(r"\b(lt\.?|left)\b", element_value, flags=re.IGNORECASE):
                side_match = "Left"
        if side_match:
            nature_entry["side"] = make_interpreted_value(side_match)
        if fragments and not natures:
            nature_entry["fragments"] = make_interpreted_value(fragments)
        natures.append(nature_entry)

    return {
        "specimen_suffix": make_interpreted_value(context.specimen_suffix or "-"),
        "storage_area": storage,
        "natures": natures,
    }


def make_identification_entry(taxon_value: str | None) -> dict[str, Any]:
    return {
        "taxon": make_interpreted_value(taxon_value),
        "verbatim_identification": make_interpreted_value(taxon_value),
    }


def build_accession_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    context = parse_accession_number(row.get("accession_number"))
    taxon_value = make_taxon_value(row)

    accession_entry: dict[str, Any] = {
        "collection_abbreviation": make_interpreted_value(
            coerce_stripped(row.get("collection_id"))
            or context.collection_abbreviation
            or "KNM"
        ),
        "specimen_prefix_abbreviation": make_interpreted_value(context.specimen_prefix),
        "specimen_no": make_interpreted_value(context.specimen_number),
        "specimen_suffix": make_interpreted_value(context.specimen_suffix),
        "type_status": make_interpreted_value(
            "Type" if normalise_yes_no(row.get("is_type_specimen")) else None
        ),
        "published": make_interpreted_value(
            "Yes" if normalise_yes_no(row.get("is_published")) else "No"
        ),
        "additional_notes": [],
        "references": build_reference_entries(row.get("reference")),
        "field_slips": [build_field_slip(row, taxon_value)],
        "rows": [build_row_section(context, row)],
        "identifications": [make_identification_entry(taxon_value)],
    }

    comment = coerce_stripped(row.get("other"))
    if comment:
        accession_entry["additional_notes"].append(
            {
                "heading": make_interpreted_value(_("Manual QC")),
                "value": make_interpreted_value(comment),
            }
        )

    return {
        "card_type": "accession_card",
        "accessions": [accession_entry],
    }


def find_media_for_row(
    row: Mapping[str, Any],
    *,
    queryset: Iterable[Media] | None = None,
) -> Media:
    identifier = coerce_stripped(row.get("id"))
    if not identifier:
        raise ManualImportError(_("Row is missing an id column"))

    candidates = {
        identifier,
        f"{identifier}.jpg",
        f"{identifier}.jpeg",
        f"{identifier}.JPG",
        f"{identifier}.JPEG",
    }

    qs = queryset if queryset is not None else Media.objects.all()
    if not isinstance(qs, QuerySet):
        try:
            iterator = iter(qs)
        except TypeError as exc:  # pragma: no cover - defensive
            raise ManualImportError("Invalid queryset provided") from exc
        matches = [media for media in iterator if getattr(media, "file_name", None) in candidates]
        if matches:
            return matches[0]
        raise ManualImportError(_("No media found for id %(identifier)s") % {"identifier": identifier})

    lookup = Q()
    for candidate in candidates:
        lookup |= Q(file_name__iexact=candidate)
    media = qs.filter(lookup).order_by("id").first()
    if not media:
        tail_lookup = Q()
        for candidate in candidates:
            tail_lookup |= Q(media_location__iendswith=f"/{candidate}") | Q(media_location__iendswith=candidate)
        media = qs.filter(tail_lookup).order_by("id").first()
    if not media:
        raise ManualImportError(_("No media found for id %(identifier)s") % {"identifier": identifier})
    return media


def parse_timestamp(value: Any) -> datetime | None:
    text = coerce_stripped(value)
    if not text:
        return None
    dt = parse_datetime(text)
    if dt is None:
        date_value = parse_date(text)
        if date_value:
            dt = datetime.combine(date_value, datetime.min.time())
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone=timezone.get_current_timezone())
    return dt


@transaction.atomic
def import_manual_row(
    row: Mapping[str, Any],
    *,
    queryset: Iterable[Media] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    media = find_media_for_row(row, queryset=queryset)
    payload = build_accession_payload(row)
    metadata = {
        "source": "manual_qc",
        "row_id": coerce_stripped(row.get("id")),
        "created_by": coerce_stripped(row.get("created_by")),
        "created_on": coerce_stripped(row.get("created_on")),
    }
    payload["_manual_import"] = metadata

    media.ocr_data = payload
    media.ocr_status = Media.OCRStatus.COMPLETED
    media.qc_status = Media.QCStatus.APPROVED

    update_fields = ["ocr_data", "ocr_status", "qc_status"]

    expert_checked_on = parse_timestamp(row.get("created_on"))
    if expert_checked_on:
        media.expert_checked_on = expert_checked_on
        update_fields.append("expert_checked_on")

    expert_identifier = coerce_stripped(row.get("created_by"))
    if expert_identifier:
        try:
            user_model = Media._meta.get_field("expert_checked_by").remote_field.model
            media.expert_checked_by = user_model.objects.get(username=expert_identifier)
            update_fields.append("expert_checked_by")
        except ObjectDoesNotExist:
            pass

    media.save(update_fields=update_fields)

    return create_accessions_from_media(media)

