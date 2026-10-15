"""Planning and execution helpers for normalising Storage area labels."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from django.db import transaction

from .merge import merge_records
from .merge.constants import MergeStrategy
from .models import Storage

LETTER_FIRST_RE = re.compile(r"^([A-Za-z]+)\s*(\d+)\s*(?:/\s*(\d+))?$")
NUMBER_FIRST_RE = re.compile(r"^(\d{2})\s*([A-Za-z])\s*(?:/\s*)?([A-Za-z])$")


def normalize_storage_token(value: str) -> str | None:
    value = value.strip()
    match = LETTER_FIRST_RE.fullmatch(value)
    if match:
        prefix, first, second = match.groups()
        return f"{prefix.upper()} {int(first + (second or ''))}"

    match = NUMBER_FIRST_RE.fullmatch(value)
    if match:
        number, first, second = match.groups()
        return f"{number} {(first + second).upper()}"

    return None


def normalize_storage_area(value: str) -> str | None:
    normalized = []
    for part in value.split("|"):
        token = normalize_storage_token(part)
        if token is None:
            return None
        if token not in normalized:
            normalized.append(token)
    return " | ".join(normalized)


@dataclass(frozen=True)
class StorageCleanGroup:
    normalized: str
    records: tuple[Storage, ...]
    parents: tuple[Storage, ...]

    @property
    def meaningful_parents(self):
        return tuple(parent for parent in self.parents if parent.area != "-Undefined")


def build_storage_clean_groups():
    grouped = defaultdict(list)
    omitted = []
    for storage in Storage.objects.select_related("parent_area").order_by("pk"):
        normalized = normalize_storage_area(storage.area)
        if normalized is None:
            omitted.append(storage)
        else:
            grouped[normalized].append(storage)
    groups = []
    for normalized, records in grouped.items():
        parents = tuple({record.parent_area for record in records if record.parent_area})
        groups.append(StorageCleanGroup(normalized, tuple(records), parents))
    return groups, omitted


def apply_storage_clean(groups, parent_choices, user):
    stats = {"groups": 0, "merged": 0, "normalized": 0, "relations": 0}
    with transaction.atomic():
        for group in groups:
            records = list(Storage.objects.select_for_update().filter(pk__in=[r.pk for r in group.records]).order_by("pk"))
            if not records:
                continue
            parent_id = parent_choices.get(group.normalized)
            parent = Storage.objects.filter(pk=parent_id).first() if parent_id else None
            target = records[0]
            target.area, target.parent_area = group.normalized, parent
            target.save(update_fields=["area", "parent_area"])
            for source in records[1:]:
                result = merge_records(
                    source, target,
                    {"fields": {"area": MergeStrategy.PREFER_NON_NULL.value, "parent_area": MergeStrategy.PREFER_NON_NULL.value}},
                    user=user,
                    archive=True,
                )
                stats["relations"] += sum(item.get("updated", 0) for item in result.relation_actions.values() if isinstance(item, dict))
                stats["merged"] += 1
            stats["groups"] += 1
            stats["normalized"] += 1
    return stats
