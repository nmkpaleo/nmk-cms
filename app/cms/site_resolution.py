"""Normalize and resolve accession collecting sites."""

import re
import unicodedata

from .models import Locality, Place, PlaceType


_NON_SITE = re.compile(
    r"(?:formation|\bfm\.?\b|member|\bmbr\.?\b|bed|horizon|tuff|comment|see notes?).*$",
    re.IGNORECASE,
)


def clean_site_area(value) -> str | None:
    if value in (None, ""):
        return None
    text = " ".join(str(value).split()).strip(" ,;|/")
    if not text:
        return None
    parts = []
    for part in re.split(r"\s*\|\s*|\s*;\s*", text):
        cleaned = _NON_SITE.sub("", part).strip(" ,;|/")
        if cleaned:
            parts.append(cleaned)
    result = " | ".join(dict.fromkeys(parts))
    return result or None


def _key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _depth(place: Place) -> int:
    depth = 0
    seen = set()
    current = place
    while current.related_place_id and current.related_place_id not in seen:
        seen.add(current.related_place_id)
        depth += 1
        current = current.related_place
    return depth


def resolve_site_area(value, locality: Locality | None = None) -> Place | None:
    cleaned = clean_site_area(value)
    if not cleaned:
        return None
    names = [_key(part) for part in cleaned.split("|") if _key(part)]
    queryset = Place.objects.filter(
        place_type__in=[PlaceType.SITE, PlaceType.COLLECTING_AREA]
    ).select_related("related_place")
    if locality is not None:
        queryset = queryset.filter(locality=locality)
    candidates = [place for place in queryset if _key(place.name) in names]
    if candidates:
        return max(candidates, key=_depth)
    if locality is None:
        return None
    return Place.objects.create(
        locality=locality,
        name=cleaned[:100],
        place_type=PlaceType.SITE,
    )
