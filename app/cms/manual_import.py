"""Utilities for importing manually curated QC rows into accession records."""

from __future__ import annotations

import re
import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q, QuerySet, Max
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext as _

from .models import Accession, Media
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
    r"^(?:(?P<collection>[A-Za-z]+)\s*[-:]\s*)?(?P<prefix>[A-Za-z]+)?[\s-]*(?P<number>\d+)"
    r"(?:[\s\-/]*(?P<suffix>[A-Za-z0-9]+(?:\s*-\s*[A-Za-z0-9]+)?))?",
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
        suffix = re.sub(r"\s+", "", suffix.upper())

    prefix = coerce_stripped(match.group("prefix"))
    if prefix:
        prefix = prefix.upper()

    collection = coerce_stripped(match.group("collection"))
    if collection:
        collection = collection.upper()

    if prefix is None and collection and "-" in value:
        # Values like "ER-30292" have the prefix separated by a hyphen but no
        # explicit collection identifier. Treat the portion before the hyphen
        # as the specimen prefix and let the collection fall back to defaults.
        prefix, collection = collection, None

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


def parse_collection_date(value: Any) -> str | None:
    text = coerce_stripped(value)
    if not text:
        return None
    if re.fullmatch(r"\d{4}", text):
        try:
            return f"{int(text):04d}-01-01"
        except ValueError:
            return None
    parsed = parse_date(text)
    if parsed:
        return parsed.isoformat()
    return text


def _convert_coordinate_component(direction: str, raw_value: str) -> str | None:
    cleaned = raw_value.replace(":", " ")
    cleaned = re.sub(r"[°º]", " ", cleaned)
    cleaned = re.sub(r"[′'’]", " ", cleaned)
    cleaned = re.sub(r"[″\"]", " ", cleaned)
    cleaned = cleaned.replace(",", " ")
    numbers = [part for part in re.split(r"\s+", cleaned) if part]
    values: list[float] = []
    for part in numbers[:3]:
        try:
            values.append(float(part))
        except (TypeError, ValueError):
            continue
    if not values:
        stripped = coerce_stripped(raw_value)
        return stripped
    degrees = values[0]
    minutes = values[1] if len(values) > 1 else 0.0
    seconds = values[2] if len(values) > 2 else 0.0
    decimal = degrees + minutes / 60 + seconds / 3600
    if direction in {"S", "W"}:
        decimal = -decimal
    formatted = f"{decimal:.6f}".rstrip("0").rstrip(".")
    return formatted or "0"


def parse_coordinates(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            latitude, longitude = parse_coordinates(item)
            if latitude or longitude:
                return latitude, longitude
        return None, None

    text = coerce_stripped(value)
    if not text:
        return None, None

    latitude: str | None = None
    longitude: str | None = None

    dir_first_pattern = re.compile(
        r"([NSEW])(?:\s*[:]\s*|\s+)([-+0-9°º.,'\"\s]+?)(?=(?:\s*[NSEW])|$)",
        flags=re.IGNORECASE,
    )

    for match in dir_first_pattern.finditer(text):
        direction = match.group(1).upper()
        raw_value = match.group(2).strip()
        if not raw_value:
            continue
        component = _convert_coordinate_component(direction, raw_value)
        if direction in {"N", "S"} and latitude is None:
            latitude = component
        elif direction in {"E", "W"} and longitude is None:
            longitude = component

    remaining = dir_first_pattern.sub(" ", text)

    dir_last_pattern = re.compile(
        r"([-+0-9°º.,'\"\s]+?)([NSEW])",
        flags=re.IGNORECASE,
    )

    for match in dir_last_pattern.finditer(remaining):
        raw_value = match.group(1).strip()
        direction = match.group(2).upper()
        if not raw_value:
            continue
        component = _convert_coordinate_component(direction, raw_value)
        if direction in {"N", "S"} and latitude is None:
            latitude = component
        elif direction in {"E", "W"} and longitude is None:
            longitude = component

    if latitude or longitude:
        return latitude, longitude

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
    if not text:
        return None
    match = re.search(r"\d+", text)
    if match:
        return match.group(0)
    return text


def _extract_reference_page(text: str | None) -> str | None:
    if not text:
        return None
    page_match = re.search(
        r"(?:pg\.?|p\.?)\s*(?P<page>[\d\-–, ]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not page_match:
        return None
    page_value = coerce_stripped(page_match.group("page"))
    if not page_value:
        return None
    return page_value[:10]


def build_reference_entries(value: Any) -> list[dict[str, dict[str, Any]]]:
    if isinstance(value, (list, tuple, set)):
        entries: list[dict[str, dict[str, Any]]] = []
        for item in value:
            entries.extend(build_reference_entries(item))
        return entries

    text = coerce_stripped(value)
    if not text:
        return []

    year_match = re.search(r"(18|19|20)\d{2}", text)
    first_author = (coerce_stripped(text.split(",", 1)[0]) or "Unknown")[:255]
    interpreted_title = text[:255]
    year = year_match.group(0) if year_match else "0000"
    page = _extract_reference_page(text)

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
        "field_number": make_interpreted_value(coerce_stripped(row.get("field_number"))),
        "collection_date": make_interpreted_value(parse_collection_date(row.get("date"))),
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
    row: Mapping[str, Any],
    specimen_suffix: str | None,
) -> dict[str, Any]:
    storage_value = coerce_stripped(row.get("storage_area") or row.get("shelf"))
    storage = make_interpreted_value(storage_value)
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
        "specimen_suffix": make_interpreted_value(specimen_suffix or "-"),
        "storage_area": storage,
        "natures": natures,
    }


QUALIFIER_TOKENS = {"cf.", "cf", "aff.", "aff", "sp.", "sp", "nr.", "nr"}


def _split_taxon_and_qualifier(value: str | None) -> tuple[str | None, str | None]:
    """Return the base taxon string and any qualifier tokens from the provided value."""

    text = coerce_stripped(value)
    if not text:
        return None, None

    tokens = text.split()
    qualifier_tokens: list[str] = []
    base_tokens: list[str] = []

    for token in tokens:
        if token.lower() in QUALIFIER_TOKENS:
            qualifier_tokens.append(token if token.endswith(".") else f"{token}.")
            continue
        base_tokens.append(token)

    qualifier = " ".join(qualifier_tokens) or None
    base_taxon = " ".join(base_tokens).strip() or None
    return base_taxon, qualifier


def _extract_lowest_taxon(row: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return (base_taxon, qualifier, verbatim_identification) derived from the row."""

    genus_value = coerce_stripped(row.get("genus"))
    species_value = coerce_stripped(row.get("species"))

    if genus_value or species_value:
        species_base, species_qualifier = _split_taxon_and_qualifier(species_value)
        genus_base, genus_qualifier = _split_taxon_and_qualifier(genus_value)
        qualifier = species_qualifier or genus_qualifier

        if species_base:
            base_taxon = " ".join(filter(None, [genus_base or genus_value, species_base]))
        elif species_value:
            base_taxon = " ".join(filter(None, [genus_base or genus_value, species_value]))
        else:
            base_taxon = genus_base or genus_value

        verbatim_identification = " ".join(filter(None, [qualifier, base_taxon])) if qualifier else base_taxon
        return base_taxon, qualifier, verbatim_identification

    for key in ("tribe", "subfamily", "family", "taxon"):
        value = coerce_stripped(row.get(key))
        if not value:
            continue
        base_taxon, qualifier = _split_taxon_and_qualifier(value)
        base_value = base_taxon or value
        verbatim_identification = " ".join(filter(None, [qualifier, base_value])) if qualifier else base_value
        return base_value, qualifier, verbatim_identification

    return None, None, None


def make_identification_entry(row: Mapping[str, Any], taxon_value: str | None) -> dict[str, Any]:
    base_taxon, qualifier, verbatim_identification = _extract_lowest_taxon(row)
    resolved_taxon = base_taxon or taxon_value
    resolved_verbatim = taxon_value or verbatim_identification or resolved_taxon

    return {
        "taxon": make_interpreted_value(resolved_taxon),
        "verbatim_identification": make_interpreted_value(resolved_verbatim),
        "taxon_verbatim": make_interpreted_value(resolved_taxon),
        "identification_qualifier": make_interpreted_value(qualifier),
    }


def _letter_code_to_number(code: str) -> int | None:
    if not code or not code.isalpha():
        return None
    result = 0
    for char in code.upper():
        result = result * 26 + (ord(char) - 64)
    return result


def _number_to_letter_code(number: int) -> str:
    if number <= 0:
        return ""
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def expand_specimen_suffix(suffix: str | None) -> list[str]:
    if not suffix or suffix == "-":
        return []
    text = suffix.upper()
    if "-" in text:
        start, end = text.split("-", 1)
        start = coerce_stripped(start)
        end = coerce_stripped(end)
        if start and end:
            start_num = _letter_code_to_number(start)
            end_num = _letter_code_to_number(end)
            if start_num is not None and end_num is not None and end_num >= start_num:
                return [_number_to_letter_code(idx) for idx in range(start_num, end_num + 1)]
    return [text]


def _unique_preserving(values: Iterable[str | None]) -> list[str | None]:
    seen: set[str | None] = set()
    result: list[str | None] = []
    for value in values:
        key = value.upper() if isinstance(value, str) else value
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _join_unique(values: Iterable[str], *, separator: str = " | ") -> str | None:
    unique = _unique_preserving(values)
    filtered = [value for value in unique if value]
    if not filtered:
        return None
    return separator.join(filtered)


def _collect_unique(rows: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    collected: list[str] = []
    for row in rows:
        value = coerce_stripped(row.get(key))
        if value and value not in collected:
            collected.append(value)
    return collected


def _format_manual_import_value(values: Sequence[str]) -> str | None:
    if not values:
        return None
    primary = coerce_stripped(values[0])
    extras = [coerce_stripped(value) for value in values[1:] if coerce_stripped(value)]
    if not primary:
        if extras:
            primary = extras.pop(0)
        else:
            return None
    if extras:
        extras_str = ", ".join(extras)
        return _("%(primary)s (others: %(others)s)") % {"primary": primary, "others": extras_str}
    return primary


def _build_manual_import_comment(
    created_by_values: Sequence[str], created_on_values: Sequence[str]
) -> str | None:
    parts: list[str] = []
    formatted_by = _format_manual_import_value(created_by_values)
    if formatted_by:
        parts.append(_("Created by %(value)s") % {"value": formatted_by})
    formatted_on = _format_manual_import_value(created_on_values)
    if formatted_on:
        parts.append(_("Created on %(value)s") % {"value": formatted_on})
    if not parts:
        return None
    return _("Manual QC import — %(details)s") % {"details": "; ".join(parts)}


def _determine_suffix_display(suffixes: list[str | None]) -> str | None:
    meaningful = [suffix for suffix in suffixes if suffix]
    if not meaningful:
        return None
    if len(meaningful) == 1:
        return meaningful[0]
    return f"{meaningful[0]}-{meaningful[-1]}"


def build_accession_payload(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ManualImportError("No rows provided for accession payload generation")

    contexts = [parse_accession_number(row.get("accession_number")) for row in rows]

    collection_values = _collect_unique(rows, "collection_id")
    collection_value = collection_values[0] if collection_values else None
    if not collection_value:
        for context in contexts:
            if context.collection_abbreviation:
                collection_value = context.collection_abbreviation
                break
    if not collection_value:
        collection_value = "KNM"

    prefix_value = None
    number_value = None
    suffix_values: list[str | None] = []
    for context in contexts:
        if context.specimen_prefix and prefix_value is None:
            prefix_value = context.specimen_prefix
        if context.specimen_number is not None and number_value is None:
            number_value = context.specimen_number
        suffix_values.extend(expand_specimen_suffix(context.specimen_suffix))

    suffixes = _unique_preserving(suffix_values)
    if not suffixes:
        suffixes = [None]
    suffix_display = _determine_suffix_display(suffixes)

    type_values = _collect_unique(rows, "is_type_specimen")
    is_type = any(normalise_yes_no(value) for value in type_values)

    published_values = _collect_unique(rows, "is_published")
    is_published = any(normalise_yes_no(value) for value in published_values)

    references = _collect_unique(rows, "reference")
    comments = _collect_unique(rows, "other")

    aggregated_row = {
        "collection_id": collection_value,
        "field_number": _join_unique(_collect_unique(rows, "field_number")),
        "date": _join_unique(_collect_unique(rows, "date")),
        "storage_area": _join_unique(
            _collect_unique(rows, "storage_area") or _collect_unique(rows, "shelf")
        ),
        "shelf": _join_unique(_collect_unique(rows, "shelf")),
        "taxon": _join_unique(_collect_unique(rows, "taxon")),
        "family": _join_unique(_collect_unique(rows, "family")),
        "subfamily": _join_unique(_collect_unique(rows, "subfamily")),
        "tribe": _join_unique(_collect_unique(rows, "tribe")),
        "genus": _join_unique(_collect_unique(rows, "genus")),
        "species": _join_unique(_collect_unique(rows, "species")),
        "body_parts": _join_unique(_collect_unique(rows, "body_parts"), separator="; "),
        "fragments": _join_unique(_collect_unique(rows, "fragments")),
        "coordinates": _collect_unique(rows, "coordinates"),
        "locality": _join_unique(_collect_unique(rows, "locality")),
        "site_area": _join_unique(_collect_unique(rows, "site_area")),
        "formation": _join_unique(_collect_unique(rows, "formation")),
        "member_horizon_level": _join_unique(_collect_unique(rows, "member_horizon_level")),
        "photo_id": _join_unique(_collect_unique(rows, "photo_id")),
    }

    taxon_value = make_taxon_value(aggregated_row)

    field_slips: list[dict[str, Any]] = []
    for row in rows:
        row_taxon_value = make_taxon_value(row)
        slip_taxon_value = row_taxon_value or taxon_value
        field_slips.append(build_field_slip(row, slip_taxon_value))

    accession_entry: dict[str, Any] = {
        "collection_abbreviation": make_interpreted_value(collection_value),
        "specimen_prefix_abbreviation": make_interpreted_value(prefix_value),
        "specimen_no": make_interpreted_value(number_value),
        "specimen_suffix": make_interpreted_value(suffix_display),
        "type_status": make_interpreted_value("Type" if is_type else None),
        "published": make_interpreted_value("Yes" if is_published else "No"),
        "additional_notes": [],
        "references": build_reference_entries(references),
        "field_slips": field_slips,
        "rows": [build_row_section(aggregated_row, suffix) for suffix in suffixes],
        "identifications": [make_identification_entry(aggregated_row, taxon_value)],
    }

    for comment in comments:
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


def _extract_accession_key(entry: Mapping[str, Any]) -> tuple[str | None, str | None, int | None]:
    collection = coerce_stripped((entry.get("collection_abbreviation") or {}).get("interpreted"))
    prefix = coerce_stripped((entry.get("specimen_prefix_abbreviation") or {}).get("interpreted"))
    specimen_no_value = (entry.get("specimen_no") or {}).get("interpreted")
    try:
        specimen_no = int(specimen_no_value) if specimen_no_value not in (None, "") else None
    except (TypeError, ValueError):
        specimen_no = None
    return collection, prefix, specimen_no


def _build_resolution_map(entry: Mapping[str, Any]) -> dict[str, dict[str, object]]:
    collection, prefix, specimen_no = _extract_accession_key(entry)
    if not collection or not prefix or specimen_no is None:
        return {}

    existing_qs = Accession.objects.filter(
        collection__abbreviation=collection,
        specimen_prefix__abbreviation=prefix,
        specimen_no=specimen_no,
    )
    if not existing_qs.exists():
        return {}

    max_instance = existing_qs.aggregate(max_instance=Max("instance_number")).get("max_instance") or 1
    key = f"{collection}:{prefix}:{specimen_no}"
    return {
        key: {
            "action": "new_instance",
            "instance_number": max_instance + 1,
        }
    }


def _find_existing_accession(entry: Mapping[str, Any]) -> Accession | None:
    collection, prefix, specimen_no = _extract_accession_key(entry)
    if specimen_no is None:
        return None

    filters: dict[str, object] = {"specimen_no": specimen_no}
    if collection:
        filters["collection__abbreviation"] = collection
    if prefix:
        filters["specimen_prefix__abbreviation"] = prefix

    return (
        Accession.objects.filter(**filters)
        .order_by("-instance_number", "-pk")
        .first()
    )


def find_media_for_row(
    row: Mapping[str, Any],
    *,
    queryset: Iterable[Media] | None = None,
) -> Media:
    identifier = coerce_stripped(row.get("id"))
    if not identifier:
        raise ManualImportError(_("Row is missing an id column"))

    qs = queryset if queryset is not None else Media.objects.all()

    base_candidates = [f"{identifier}.jpg", f"{identifier}.jpeg"]
    manual_paths = [f"uploads/manual_qc/{name}" for name in base_candidates]

    manual_paths_lower = {path.lower() for path in manual_paths}
    name_candidates_lower = {name.lower() for name in base_candidates}

    def _from_iterable(iterable: Iterable[Media]) -> Media | None:
        for media in iterable:
            file_name = getattr(media, "file_name", "")
            media_path = getattr(media.media_location, "name", "")
            if media_path and media_path.lower() in manual_paths_lower:
                return media
            if file_name and file_name.lower() in name_candidates_lower:
                return media
        return None

    if not isinstance(qs, QuerySet):
        try:
            iterator = iter(qs)
        except TypeError as exc:  # pragma: no cover - defensive
            raise ManualImportError("Invalid queryset provided") from exc
        match = _from_iterable(iterator)
        if match:
            return match
        raise ManualImportError(_("No media found for id %(identifier)s") % {"identifier": identifier})

    path_lookup = Q()
    for path in manual_paths:
        path_lookup |= Q(media_location__iexact=path)
    media = qs.filter(path_lookup).order_by("-id").first()

    if not media:
        name_lookup = Q()
        for name in base_candidates:
            name_lookup |= Q(file_name__iexact=name)
        media = qs.filter(name_lookup).order_by("-id").first()

    if not media:
        fallback_lookup = Q()
        for name in base_candidates:
            fallback_lookup |= Q(media_location__iendswith=f"/{name}") | Q(media_location__iendswith=name)
        media = qs.filter(fallback_lookup).order_by("-id").first()

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
    rows: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    queryset: Iterable[Media] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if isinstance(rows, Mapping):
        row_list: list[Mapping[str, Any]] = [rows]
    else:
        row_list = list(rows)

    if not row_list:
        raise ManualImportError(_("Manual import row group is empty"))

    medias = [find_media_for_row(row, queryset=queryset) for row in row_list]
    payload = build_accession_payload(row_list)

    row_ids = [coerce_stripped(row.get("id")) for row in row_list if coerce_stripped(row.get("id"))]
    created_by_values = _collect_unique(row_list, "created_by")
    created_on_values = _collect_unique(row_list, "created_on")

    metadata = {
        "source": "manual_qc",
        "row_ids": row_ids,
        "group_size": len(row_list),
    }

    if row_ids:
        metadata["row_id"] = row_ids[0]
    if created_by_values:
        metadata["created_by"] = created_by_values[0]
        if len(created_by_values) > 1:
            metadata["created_by_values"] = created_by_values
    if created_on_values:
        metadata["created_on"] = created_on_values[0]
        if len(created_on_values) > 1:
            metadata["created_on_values"] = created_on_values

    payload["_manual_import"] = metadata

    accession_entry = (payload.get("accessions") or [{}])[0]
    resolution_map = _build_resolution_map(accession_entry)

    result: dict[str, list[dict[str, Any]]] | None = None
    primary_accession = None

    processed_medias: list[Media] = []

    for index, (row, media) in enumerate(zip(row_list, medias)):
        row_payload = copy.deepcopy(payload)
        row_metadata = dict(row_payload.get("_manual_import", {}))
        identifier = coerce_stripped(row.get("id"))
        if identifier:
            row_metadata["row_id"] = identifier
        row_metadata["group_index"] = index
        row_metadata["primary"] = index == 0
        row_payload["_manual_import"] = row_metadata

        media.ocr_data = row_payload
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

        if index == 0:
            result = create_accessions_from_media(media, resolution_map=resolution_map)
            primary_accession = getattr(media, "accession", None)
            if primary_accession is None:
                created_entries = (result or {}).get("created") or []
                for entry in created_entries:
                    accession_id = entry.get("accession_id")
                    if accession_id:
                        candidate = Accession.objects.filter(pk=accession_id).first()
                        if candidate:
                            primary_accession = candidate
                            break
            if primary_accession and media.accession_id != getattr(primary_accession, "pk", None):
                media.accession = primary_accession
                media.save(update_fields=["accession"])

        processed_medias.append(media)

    accession_obj = None
    if primary_accession is not None:
        if hasattr(primary_accession, "pk"):
            accession_obj = primary_accession
        else:
            accession_obj = Accession.objects.filter(pk=primary_accession).first()

    if accession_obj is None:
        accession_obj = _find_existing_accession(accession_entry)

    if accession_obj:
        media_ids = [media.pk for media in processed_medias if getattr(media, "pk", None)]
        if media_ids:
            Media.objects.filter(pk__in=media_ids).update(accession=accession_obj)
            for media in processed_medias:
                media.accession = accession_obj
                media.accession_id = accession_obj.pk
        comment_text = _build_manual_import_comment(created_by_values, created_on_values)
        if comment_text:
            _append_manual_import_comment(
                accession_obj,
                comment_text,
                additional_accessions=_gather_additional_accessions(result, accession_obj),
            )
    else:
        conflicts = (result or {}).get("conflicts") if result else []
        if conflicts:
            reasons = ", ".join(filter(None, (conflict.get("reason") for conflict in conflicts)))
            raise ManualImportError(
                _("Unable to create accession for manual QC rows (%(reason)s)")
                % {"reason": reasons or "unknown"}
            )
        raise ManualImportError(_("Manual QC import did not produce an accession"))

    return result or {}


def _gather_additional_accessions(
    result: dict[str, list[dict[str, Any]]] | None,
    primary_accession: Accession,
) -> list[Accession]:
    if not result:
        return []

    primary_pk = getattr(primary_accession, "pk", None)
    accession_ids: set[int] = set()

    for key in ("created", "updated"):
        for entry in result.get(key, []) or []:
            accession_id = entry.get("accession_id")
            if accession_id and accession_id != primary_pk:
                accession_ids.add(accession_id)

    if not accession_ids:
        return []

    return list(Accession.objects.filter(pk__in=accession_ids))


def _append_manual_import_comment(
    accession: Accession,
    comment_text: str | None,
    *,
    additional_accessions: Sequence[Accession] | None = None,
) -> None:
    if not comment_text:
        return

    targets: list[Accession] = []

    if accession is not None:
        targets.append(accession)

    if additional_accessions:
        for extra in additional_accessions:
            if extra is not None:
                targets.append(extra)

    seen: set[int] = set()

    for target in targets:
        pk = getattr(target, "pk", None)
        if pk is not None:
            if pk in seen:
                continue
            seen.add(pk)

        existing = target.comment or ""
        if comment_text in existing:
            continue
        if existing:
            new_comment = f"{existing.rstrip()}\n{comment_text}"
        else:
            new_comment = comment_text
        target.comment = new_comment
        target.save(update_fields=["comment"])

