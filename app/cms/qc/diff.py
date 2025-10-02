from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Sequence, Tuple

_METADATA_PREFIX = "_"


def interpreted_value(value: Any) -> Any:
    """Return the interpreted value from OCR payload entries."""

    if isinstance(value, dict):
        if "interpreted" in value:
            return value.get("interpreted")
        return None
    return value


def ident_payload_has_meaningful_data(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in (
        "taxon",
        "identification_qualifier",
        "verbatim_identification",
        "identification_remarks",
        "identified_by",
        "reference",
        "date_identified",
    ):
        if interpreted_value(entry.get(key)) not in (None, ""):
            return True
    return False


def _is_metadata_key(key: str | None) -> bool:
    return bool(key) and key.startswith(_METADATA_PREFIX)


def _strip_metadata(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_metadata(value)
            for key, value in payload.items()
            if not _is_metadata_key(key)
        }
    if isinstance(payload, list):
        return [_strip_metadata(value) for value in payload]
    return payload


def iter_field_diffs(old: Any, new: Any, path: str = "") -> Iterator[Tuple[str, Any, Any]]:
    """Yield differences between two payload structures."""

    if isinstance(new, dict) and not isinstance(old, dict):
        old = {}
    if isinstance(new, list) and not isinstance(old, list):
        old = []

    if isinstance(old, dict) and isinstance(new, dict):
        keys = set(old.keys()) | set(new.keys())
        for key in sorted(keys):
            if _is_metadata_key(key):
                continue
            if key == "interpreted":
                old_val = old.get("interpreted")
                new_val = new.get("interpreted")
                if old_val != new_val:
                    yield path, old_val, new_val
                continue
            sub_path = f"{path}.{key}" if path else key
            yield from iter_field_diffs(old.get(key), new.get(key), sub_path)
    elif isinstance(old, list) and isinstance(new, list):
        length = max(len(old), len(new))
        for index in range(length):
            old_value = old[index] if index < len(old) else None
            new_value = new[index] if index < len(new) else None
            sub_path = f"{path}[{index}]" if path else f"[{index}]"
            yield from iter_field_diffs(old_value, new_value, sub_path)
    else:
        if old != new:
            yield path, old, new


@dataclass(frozen=True)
class _CountDiff:
    key: str
    label: str
    original: int
    current: int

    @property
    def changed(self) -> bool:
        return self.original != self.current

    @property
    def delta(self) -> int:
        return self.current - self.original

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "original": self.original,
            "current": self.current,
            "changed": self.changed,
            "delta": self.delta,
        }


def _get_accession_payload(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return {}
    accessions = data.get("accessions")
    if isinstance(accessions, list) and accessions:
        first = accessions[0]
        if isinstance(first, dict):
            return first
    return {}


def _list_or_empty(value: Any) -> list:
    return value if isinstance(value, list) else []


def _row_key(row: dict | None, index: int) -> str:
    if not isinstance(row, dict):
        return f"index::{index}"
    for key_name in ("_row_id", "row_id"):
        value = row.get(key_name)
        if value not in (None, ""):
            return str(value)
    suffix = interpreted_value(row.get("specimen_suffix"))
    if suffix not in (None, ""):
        return f"suffix::{suffix}"
    return f"index::{index}"


def _row_has_meaningful_data(row: dict | None) -> bool:
    if not isinstance(row, dict):
        return False
    if interpreted_value(row.get("specimen_suffix")) not in (None, "", "-"):
        return True
    if interpreted_value(row.get("storage_area")) not in (None, ""):
        return True
    natures = _list_or_empty(row.get("natures"))
    for nature in natures:
        if not isinstance(nature, dict):
            continue
        for key in (
            "element_name",
            "side",
            "condition",
            "verbatim_element",
            "portion",
            "fragments",
        ):
            if interpreted_value(nature.get(key)) not in (None, ""):
                return True
    return False


def _count_rows(rows: Sequence[dict]) -> int:
    return len(rows)


def _count_identifications(entries: Sequence[dict]) -> int:
    return sum(1 for entry in entries if ident_payload_has_meaningful_data(entry))


def _count_specimens(rows: Sequence[dict]) -> int:
    total = 0
    for row in rows:
        natures = _list_or_empty(row.get("natures"))
        total += sum(1 for nature in natures if isinstance(nature, dict))
    return total


def _entry_has_meaningful_data(entry: dict | None, keys: Iterable[str]) -> bool:
    if not isinstance(entry, dict):
        return False
    return any(interpreted_value(entry.get(key)) not in (None, "") for key in keys)


def _count_references(entries: Sequence[dict]) -> int:
    return sum(
        1
        for entry in entries
        if _entry_has_meaningful_data(
            entry,
            ("reference_first_author", "reference_title", "reference_year", "page"),
        )
    )


def _count_field_slips(entries: Sequence[dict]) -> int:
    return sum(
        1
        for entry in entries
        if _entry_has_meaningful_data(
            entry,
            (
                "field_number",
                "verbatim_locality",
                "verbatim_taxon",
                "verbatim_element",
                "aerial_photo",
                "verbatim_latitude",
                "verbatim_longitude",
                "verbatim_elevation",
            ),
        )
        or _entry_has_meaningful_data(
            entry.get("verbatim_horizon"),
            ("formation", "member", "bed_or_horizon", "chronostratigraphy"),
        )
    )


def _build_count_diffs(original_payload: dict, current_payload: dict) -> List[dict[str, Any]]:
    original_rows = _list_or_empty(original_payload.get("rows"))
    current_rows = _list_or_empty(current_payload.get("rows"))
    original_idents = _list_or_empty(original_payload.get("identifications"))
    current_idents = _list_or_empty(current_payload.get("identifications"))
    original_refs = _list_or_empty(original_payload.get("references"))
    current_refs = _list_or_empty(current_payload.get("references"))
    original_field_slips = _list_or_empty(original_payload.get("field_slips"))
    current_field_slips = _list_or_empty(current_payload.get("field_slips"))

    diffs = [
        _CountDiff(
            key="rows",
            label="Specimen rows",
            original=_count_rows(original_rows),
            current=_count_rows(current_rows),
        ),
        _CountDiff(
            key="identifications",
            label="Identifications",
            original=_count_identifications(original_idents),
            current=_count_identifications(current_idents),
        ),
        _CountDiff(
            key="specimens",
            label="Specimen records",
            original=_count_specimens(original_rows),
            current=_count_specimens(current_rows),
        ),
        _CountDiff(
            key="references",
            label="References",
            original=_count_references(original_refs),
            current=_count_references(current_refs),
        ),
        _CountDiff(
            key="field_slips",
            label="Field slips",
            original=_count_field_slips(original_field_slips),
            current=_count_field_slips(current_field_slips),
        ),
    ]
    return [diff.as_dict() for diff in diffs]


def _detect_rows_reordered(original_payload: dict, current_payload: dict) -> bool:
    original_rows = _list_or_empty(original_payload.get("rows"))
    current_rows = _list_or_empty(current_payload.get("rows"))
    original_keys = [_row_key(row, index) for index, row in enumerate(original_rows)]
    current_keys = [_row_key(row, index) for index, row in enumerate(current_rows)]

    filtered_current = [key for key in current_keys if key in original_keys]
    trimmed_original = original_keys[: len(filtered_current)]
    return filtered_current != trimmed_original and bool(filtered_current)


def _detect_removed_identifications(
    original_payload: dict, current_payload: dict
) -> List[dict[str, Any]]:
    original_rows = _list_or_empty(original_payload.get("rows"))
    current_rows = _list_or_empty(current_payload.get("rows"))
    original_identifications = _list_or_empty(original_payload.get("identifications"))

    removed_indexes: List[int] = []
    if len(original_identifications) > len(current_rows):
        for index in range(len(current_rows), len(original_identifications)):
            if ident_payload_has_meaningful_data(original_identifications[index]):
                removed_indexes.append(index)

    if not removed_indexes:
        return []

    count = len(removed_indexes)
    message = (
        "{} identification record{} no longer match a specimen row.".format(
            count, "s" if count != 1 else ""
        )
    )
    return [
        {
            "code": "unlinked_identifications",
            "label": "Unlinked identifications",
            "count": count,
            "message": message,
        }
    ]


def diff_media_payload(
    original: dict | None,
    current: dict | None,
    *,
    rows_reordered: bool | None = None,
) -> dict[str, Any]:
    """Return a rich diff summary between two media payloads."""

    original = original or {}
    current = current or {}

    stripped_original = _strip_metadata(original)
    stripped_current = _strip_metadata(current)

    original_accession = _get_accession_payload(stripped_original)
    current_accession = _get_accession_payload(stripped_current)

    field_diffs = list(iter_field_diffs(stripped_original, stripped_current))
    if rows_reordered is None:
        rows_reordered = _detect_rows_reordered(original_accession, current_accession)

    count_diffs = _build_count_diffs(original_accession, current_accession)
    warnings: List[dict[str, Any]] = _detect_removed_identifications(
        original_accession, current_accession
    )

    return {
        "field_diffs": field_diffs,
        "rows_reordered": bool(rows_reordered),
        "count_diffs": count_diffs,
        "warnings": warnings,
    }
