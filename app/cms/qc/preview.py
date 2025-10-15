from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from django.contrib.auth import get_user_model

from cms.models import Collection, Locality, Taxon

from .diff import ident_payload_has_meaningful_data, interpreted_value

User = get_user_model()


class PreviewMediaRelation:
    def all(self) -> list:
        return []


@dataclass
class PreviewTaxonomy:
    family: Optional[str] = None
    subfamily: Optional[str] = None
    tribe: Optional[str] = None
    genus: Optional[str] = None
    species: Optional[str] = None


@dataclass
class PreviewNature:
    element: Optional[str]
    side: Optional[str]
    condition: Optional[str]
    verbatim_element: Optional[str]
    portion: Optional[str]
    fragments: Optional[str]


@dataclass
class PreviewFieldSlip:
    id: str
    field_number: Optional[str]
    verbatim_locality: Optional[str]
    verbatim_taxon: Optional[str]
    verbatim_element: Optional[str]
    horizon_formation: Optional[str]
    horizon_member: Optional[str]
    horizon_bed: Optional[str]
    horizon_chronostratigraphy: Optional[str]
    aerial_photo: Optional[str]
    verbatim_latitude: Optional[str]
    verbatim_longitude: Optional[str]
    verbatim_elevation: Optional[str]


class PreviewNatureManager:
    def __init__(self, items: Iterable[PreviewNature]):
        self._items = list(items)

    def all(self) -> List[PreviewNature]:
        return list(self._items)


@dataclass
class PreviewAccessionRow:
    id: str
    specimen_suffix: Optional[str]
    storage: Optional[str]
    natureofspecimen_set: PreviewNatureManager


@dataclass
class PreviewIdentification:
    id: str
    taxon: Optional[str]
    identification_qualifier: Optional[str]
    verbatim_identification: Optional[str]
    identification_remarks: Optional[str]


class PreviewAccession:
    def __init__(
        self,
        collection_abbr: Optional[str],
        prefix_obj: Optional[Locality | str],
        specimen_no: Optional[int | str],
        type_status: Optional[str],
        comment: Optional[str],
        accessioned_by: Optional[User],
    ) -> None:
        self.collection_abbr = collection_abbr or ""
        self.specimen_prefix = prefix_obj
        self.specimen_no = specimen_no
        self.type_status = type_status
        self.comment = comment
        self.accessioned_by = accessioned_by
        self.media = PreviewMediaRelation()
        self.instance_number = 1

    def __str__(self) -> str:
        prefix_display = str(self.specimen_prefix or "")
        specimen_value = self.specimen_no or ""
        base = f"{self.collection_abbr}-{prefix_display} {specimen_value}".strip()
        return base or "Preview accession"


def _get_accession_payload(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return {}
    accessions = data.get("accessions")
    if isinstance(accessions, list) and accessions:
        first = accessions[0]
        if isinstance(first, dict):
            return first
    return {}


def _build_preview_rows(payload: dict) -> tuple[List[PreviewAccessionRow], Dict[str, PreviewIdentification], Dict[str, int], Dict[str, object]]:
    rows_payload = payload.get("rows") or []
    ident_payload = payload.get("identifications") or []

    rows: List[PreviewAccessionRow] = []
    first_identifications: Dict[str, PreviewIdentification] = {}
    identification_counts: Dict[str, int] = {}
    taxonomy_map: Dict[str, object] = {}

    for index, row in enumerate(rows_payload):
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("_row_id") or row.get("row_id") or f"row-{index}")
        specimen_suffix = interpreted_value(row.get("specimen_suffix"))
        storage = interpreted_value(row.get("storage_area"))
        natures_payload = row.get("natures") or []
        natures: List[PreviewNature] = []
        for nature in natures_payload:
            if not isinstance(nature, dict):
                continue
            natures.append(
                PreviewNature(
                    element=interpreted_value(nature.get("element_name")),
                    side=interpreted_value(nature.get("side")),
                    condition=interpreted_value(nature.get("condition")),
                    verbatim_element=interpreted_value(nature.get("verbatim_element")),
                    portion=interpreted_value(nature.get("portion")),
                    fragments=interpreted_value(nature.get("fragments")),
                )
            )
        row_obj = PreviewAccessionRow(
            id=row_id,
            specimen_suffix=specimen_suffix,
            storage=storage,
            natureofspecimen_set=PreviewNatureManager(natures),
        )
        rows.append(row_obj)

        ident_entry = ident_payload[index] if index < len(ident_payload) else {}
        if ident_payload_has_meaningful_data(ident_entry):
            ident_obj = PreviewIdentification(
                id=f"{row_id}-ident",
                taxon=interpreted_value(ident_entry.get("taxon")),
                identification_qualifier=interpreted_value(ident_entry.get("identification_qualifier")),
                verbatim_identification=interpreted_value(ident_entry.get("verbatim_identification")),
                identification_remarks=interpreted_value(ident_entry.get("identification_remarks")),
            )
            first_identifications[row_id] = ident_obj
            identification_counts[row_id] = 1
            taxon_name = ident_obj.taxon
            if taxon_name:
                taxonomy_map[ident_obj.id] = (
                    Taxon.objects.filter(taxon_name__iexact=taxon_name).first()
                    or PreviewTaxonomy()
                )
            else:
                taxonomy_map[ident_obj.id] = PreviewTaxonomy()
        else:
            identification_counts[row_id] = 0

    return rows, first_identifications, identification_counts, taxonomy_map


def _build_preview_fieldslips(payload: dict) -> List[PreviewFieldSlip]:
    field_slips_payload = payload.get("field_slips") or []
    field_slips: List[PreviewFieldSlip] = []

    for index, entry in enumerate(field_slips_payload):
        if not isinstance(entry, dict):
            continue

        slip_id = str(entry.get("_field_slip_id") or f"field-slip-{index}")
        horizon_payload = entry.get("verbatim_horizon") or {}

        field_slips.append(
            PreviewFieldSlip(
                id=slip_id,
                field_number=interpreted_value(entry.get("field_number")),
                verbatim_locality=interpreted_value(entry.get("verbatim_locality")),
                verbatim_taxon=interpreted_value(entry.get("verbatim_taxon")),
                verbatim_element=interpreted_value(entry.get("verbatim_element")),
                horizon_formation=interpreted_value((horizon_payload or {}).get("formation")),
                horizon_member=interpreted_value((horizon_payload or {}).get("member")),
                horizon_bed=interpreted_value((horizon_payload or {}).get("bed_or_horizon")),
                horizon_chronostratigraphy=interpreted_value((horizon_payload or {}).get("chronostratigraphy")),
                aerial_photo=interpreted_value(entry.get("aerial_photo")),
                verbatim_latitude=interpreted_value(entry.get("verbatim_latitude")),
                verbatim_longitude=interpreted_value(entry.get("verbatim_longitude")),
                verbatim_elevation=interpreted_value(entry.get("verbatim_elevation")),
            )
        )

    return field_slips


def _build_preview_references(payload: dict) -> List[object]:
    references_payload = payload.get("references") or []
    references: List[object] = []
    for entry in references_payload:
        if not isinstance(entry, dict):
            continue
        reference = type(
            "PreviewReferenceDetails",
            (),
            {
                "year": interpreted_value(entry.get("reference_year")),
                "first_author": interpreted_value(entry.get("reference_first_author")),
                "title": interpreted_value(entry.get("reference_title")),
            },
        )()
        record = type(
            "PreviewReference",
            (),
            {
                "reference": reference,
                "page": interpreted_value(entry.get("page")),
            },
        )()
        references.append(record)
    return references


def _resolve_prefix(abbreviation: Optional[str]) -> Optional[object]:
    if not abbreviation:
        return None
    locality = Locality.objects.filter(abbreviation=abbreviation).first()
    if locality:
        return locality
    return abbreviation


def _resolve_collection_abbr(abbreviation: Optional[str]) -> Optional[str]:
    if not abbreviation:
        return None
    collection = Collection.objects.filter(abbreviation=abbreviation).first()
    if collection:
        return collection.abbreviation
    return abbreviation


def _resolve_accessioned_by(form, request_user) -> Optional[User]:
    if form is not None:
        if hasattr(form, "is_valid") and form.is_bound and form.is_valid():
            value = form.cleaned_data.get("accessioned_by")
            if value:
                return value
        initial = getattr(form, "initial", {}) or {}
        value = initial.get("accessioned_by")
        if value:
            return value
    return request_user if isinstance(request_user, User) else None


def build_preview_accession(
    payload: dict | None,
    accession_form=None,
    *,
    request_user=None,
) -> dict[str, object]:
    accession_payload = _get_accession_payload(payload)

    collection_abbr = interpreted_value(accession_payload.get("collection_abbreviation"))
    prefix_abbr = interpreted_value(accession_payload.get("specimen_prefix_abbreviation"))
    specimen_no = interpreted_value(accession_payload.get("specimen_no"))
    type_status = interpreted_value(accession_payload.get("type_status"))
    comment = interpreted_value(accession_payload.get("comment"))

    try:
        specimen_no_display = int(specimen_no)
    except (TypeError, ValueError):
        specimen_no_display = specimen_no

    accessioned_by = _resolve_accessioned_by(accession_form, request_user)

    accession_obj = PreviewAccession(
        collection_abbr=_resolve_collection_abbr(collection_abbr),
        prefix_obj=_resolve_prefix(prefix_abbr),
        specimen_no=specimen_no_display,
        type_status=type_status,
        comment=comment,
        accessioned_by=accessioned_by,
    )

    rows, first_identifications, identification_counts, taxonomy_map = _build_preview_rows(
        accession_payload
    )
    references = _build_preview_references(accession_payload)
    field_slips = _build_preview_fieldslips(accession_payload)

    return {
        "accession": accession_obj,
        "geologies": [],
        "accession_rows": rows,
        "first_identifications": first_identifications,
        "identification_counts": identification_counts,
        "taxonomy": taxonomy_map,
        "references": references,
        "fieldslips": field_slips,
    }
