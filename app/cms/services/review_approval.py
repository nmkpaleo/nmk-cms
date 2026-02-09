from __future__ import annotations

import json
from dataclasses import dataclass
import os
from typing import Any

from crum import set_current_user
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cms.manual_import import parse_accession_number
from cms.models import (
    Accession,
    AccessionFieldSlip,
    AccessionRow,
    Collection,
    Element,
    Identification,
    Locality,
    Media,
    NatureOfSpecimen,
    SpecimenListPage,
    SpecimenListRowCandidate,
)
from cms.ocr_processing import _ensure_field_slip


@dataclass
class ApprovalResult:
    row_id: int
    accession_id: int | None
    accession_row_id: int | None
    field_slip_id: int | None
    accession_fieldslip_id: int | None
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "accession_id": self.accession_id,
            "accession_row_id": self.accession_row_id,
            "field_slip_id": self.field_slip_id,
            "accession_fieldslip_id": self.accession_fieldslip_id,
            "errors": self.errors,
        }


def _normalise_row_data(data: dict[str, Any]) -> dict[str, Any]:
    normalised: dict[str, Any] = {}
    for key, value in data.items():
        if str(key).startswith("_"):
            continue
        normalised[str(key).strip().lower()] = value
    accession_number = normalised.get("accession_number")
    if accession_number not in (None, ""):
        cleaned_accession = str(accession_number).strip()
        if not cleaned_accession.upper().startswith("KNM-"):
            cleaned_accession = f"KNM-{cleaned_accession}"
        normalised["accession_number"] = cleaned_accession
    return normalised


def _validate_row_data(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    accession_number = data.get("accession_number")
    if accession_number in (None, ""):
        errors.append(str(_("Accession number is required.")))
    return errors


def _build_accession(row_data: dict[str, Any]) -> tuple[Accession | None, list[str]]:
    errors: list[str] = []
    accession_number = row_data.get("accession_number")
    if accession_number in (None, ""):
        return None, [str(_("Accession number is required."))]

    context = parse_accession_number(accession_number)
    collection_abbr = context.collection_abbreviation or "KNM"
    collection = Collection.objects.filter(abbreviation=collection_abbr).first()
    if not collection:
        errors.append(str(_("Collection %(abbr)s not found.") % {"abbr": collection_abbr}))
        return None, errors

    prefix_abbr = context.specimen_prefix
    if not prefix_abbr:
        errors.append(str(_("Specimen prefix is required.")))
        return None, errors
    specimen_prefix = Locality.objects.filter(abbreviation=prefix_abbr).first()
    if not specimen_prefix:
        specimen_prefix = Locality.objects.create(
            abbreviation=prefix_abbr,
            name=str(_("Temporary Locality %(abbr)s")) % {"abbr": prefix_abbr},
        )

    specimen_no = context.specimen_number
    if specimen_no is None:
        errors.append(str(_("Specimen number is required.")))
        return None, errors

    accession, _ = Accession.objects.get_or_create(
        collection=collection,
        specimen_prefix=specimen_prefix,
        specimen_no=specimen_no,
        defaults={"instance_number": 1},
    )
    if _coerce_boolean(row_data.get("red_dot")):
        Accession.objects.filter(pk=accession.pk).update(is_published=True)
    return accession, errors


def _build_accession_row(accession: Accession, row_data: dict[str, Any]) -> AccessionRow:
    context = parse_accession_number(row_data.get("accession_number"))
    suffix = context.specimen_suffix or "-"
    accession_row, _ = AccessionRow.objects.get_or_create(
        accession=accession,
        specimen_suffix=suffix,
    )
    return accession_row


def _build_field_slip(row_data: dict[str, Any]) -> tuple[AccessionFieldSlip | None, list[str]]:
    errors: list[str] = []
    accession = row_data.get("accession")
    if accession is None:
        errors.append(str(_("Accession is required for field slip creation.")))
        return None, errors
    slip_data = {
        "field_number": row_data.get("field_number"),
        "verbatim_locality": row_data.get("locality"),
        "verbatim_taxon": row_data.get("taxon"),
        "verbatim_element": row_data.get("element") or row_data.get("verbatim_element"),
        "collection_date": row_data.get("date"),
    }
    field_slip = _ensure_field_slip(slip_data)
    if not field_slip:
        errors.append(str(_("Field slip data is incomplete.")))
        return None, errors
    accession_field_slip, _ = AccessionFieldSlip.objects.get_or_create(
        accession=accession,
        fieldslip=field_slip,
    )
    review_comment = row_data.get("review_comment")
    if review_comment not in (None, ""):
        existing_notes = accession_field_slip.notes or ""
        updated_notes = "\n\n".join(
            part for part in [existing_notes, str(review_comment).strip()] if part
        )
        if updated_notes != existing_notes:
            accession_field_slip.notes = updated_notes
            accession_field_slip.save(update_fields=["notes"])
    return accession_field_slip, errors


def _build_identification(accession_row: AccessionRow, row_data: dict[str, Any]) -> None:
    taxon = row_data.get("taxon")
    if taxon in (None, ""):
        return
    Identification.objects.get_or_create(
        accession_row=accession_row,
        taxon_verbatim=str(taxon).strip(),
        defaults={"taxon": str(taxon).strip()},
    )


def _build_nature_of_specimen(accession_row: AccessionRow, row_data: dict[str, Any]) -> None:
    element_name = row_data.get("element") or row_data.get("verbatim_element")
    if element_name in (None, ""):
        return
    cleaned_name = str(element_name).strip()
    element = Element.objects.filter(name__iexact=cleaned_name).first()
    if not element:
        element = Element.objects.filter(name="-Undefined").first()
        if element is None:
            element = Element.objects.create(name="-Undefined")
    verbatim_element = row_data.get("verbatim_element") or cleaned_name
    NatureOfSpecimen.objects.get_or_create(
        accession_row=accession_row,
        element=element,
        defaults={
            "side": row_data.get("side"),
            "condition": row_data.get("condition"),
            "verbatim_element": verbatim_element,
            "portion": row_data.get("portion"),
            "fragments": 0,
        },
    )


def _store_row_draft(row: SpecimenListRowCandidate, row_data: dict[str, Any]) -> None:
    row.data = dict(row.data or {})
    row.data["_draft"] = {
        "saved_at": timezone.now().isoformat(),
        "data": row_data,
    }
    row.save(update_fields=["data", "updated_at"])


def _coerce_boolean(value: object) -> bool:
    if value in (True, False):
        return bool(value)
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ensure_media_for_page(
    *,
    page: SpecimenListPage,
    accession: Accession | None,
    accession_row: AccessionRow | None,
    reviewer,
) -> None:
    if not page.image_file:
        return
    if accession is None and accession_row is None:
        return
    existing = Media.objects.filter(
        accession=accession,
        accession_row=accession_row,
        media_location=page.image_file.name,
    ).first()
    if existing:
        return
    file_name = os.path.basename(page.image_file.name)
    _, extension = os.path.splitext(file_name)
    media_format = extension.lstrip(".").lower() if extension else None
    set_current_user(reviewer)
    try:
        Media.objects.create(
            accession=accession,
            accession_row=accession_row,
            file_name=file_name,
            type="document",
            format=media_format or None,
            media_location=page.image_file,
        )
    finally:
        set_current_user(None)


def _store_row_result(row: SpecimenListRowCandidate, result: ApprovalResult) -> None:
    row.data = dict(row.data or {})
    row.data["_import_result"] = result.as_dict()
    row.status = (
        SpecimenListRowCandidate.ReviewStatus.APPROVED
        if not result.errors
        else SpecimenListRowCandidate.ReviewStatus.REJECTED
    )
    row.save(update_fields=["data", "status", "updated_at"])


def _store_page_results(
    page: SpecimenListPage, results: list[ApprovalResult], reviewer
) -> None:
    summary = {
        "approved_at": timezone.now().isoformat(),
        "results": [result.as_dict() for result in results],
    }
    existing_notes = page.classification_notes or ""
    page.classification_notes = "\n\n".join(
        part for part in [existing_notes, json.dumps(summary, ensure_ascii=False)] if part
    )
    set_current_user(reviewer)
    try:
        page.save(update_fields=["classification_notes"])
    finally:
        set_current_user(None)


def _move_page_image(page: SpecimenListPage, reviewer) -> None:
    if not page.image_file:
        return
    current_name = page.image_file.name
    if "/pages/approved/" in current_name:
        return
    new_name = current_name.replace("/pages/", "/pages/approved/", 1)
    with page.image_file.open("rb") as handle:
        content = ContentFile(handle.read())
    stored_name = default_storage.save(new_name, content)
    if stored_name != current_name:
        default_storage.delete(current_name)
    page.image_file.name = stored_name
    set_current_user(reviewer)
    try:
        page.save(update_fields=["image_file"])
    finally:
        set_current_user(None)


def approve_row(*, row: SpecimenListRowCandidate, reviewer) -> ApprovalResult:
    row_data = _normalise_row_data(row.data or {})
    errors = _validate_row_data(row_data)
    if errors:
        result = ApprovalResult(
            row_id=row.id,
            accession_id=None,
            accession_row_id=None,
            field_slip_id=None,
            accession_fieldslip_id=None,
            errors=errors,
        )
        _store_row_result(row, result)
        return result

    _store_row_draft(row, row_data)

    set_current_user(reviewer)
    try:
        accession, accession_errors = _build_accession(row_data)
        errors.extend(accession_errors)
    finally:
        set_current_user(None)
    accession_row_id = None
    field_slip_id = None
    accession_fieldslip_id = None
    if accession:
        set_current_user(reviewer)
        try:
            accession_row = _build_accession_row(accession, row_data)
        finally:
            set_current_user(None)
        accession_row_id = accession_row.id

        set_current_user(reviewer)
        try:
            _build_identification(accession_row, row_data)
            _build_nature_of_specimen(accession_row, row_data)
        finally:
            set_current_user(None)

        slip_data = dict(row_data)
        slip_data["accession"] = accession
        set_current_user(reviewer)
        try:
            accession_field_slip, slip_errors = _build_field_slip(slip_data)
        finally:
            set_current_user(None)
        errors.extend(slip_errors)
        if accession_field_slip:
            accession_fieldslip_id = accession_field_slip.id
            field_slip_id = accession_field_slip.fieldslip_id

    result = ApprovalResult(
        row_id=row.id,
        accession_id=accession.id if accession else None,
        accession_row_id=accession_row_id,
        field_slip_id=field_slip_id,
        accession_fieldslip_id=accession_fieldslip_id,
        errors=errors,
    )
    _store_row_result(row, result)
    return result


def approve_page(*, page: SpecimenListPage, reviewer) -> list[ApprovalResult]:
    results: list[ApprovalResult] = []
    now_time = timezone.now()
    with transaction.atomic():
        page = (
            SpecimenListPage.objects.select_for_update()
            .select_related("pdf", "assigned_reviewer")
            .get(pk=page.pk)
        )
        rows = page.row_candidates.all().order_by("row_index")
        for row in rows:
            results.append(approve_row(row=row, reviewer=reviewer))

        for accession_id, accession_row_id in {
            (result.accession_id, result.accession_row_id) for result in results
        }:
            accession = (
                Accession.objects.filter(pk=accession_id).first() if accession_id else None
            )
            accession_row = (
                AccessionRow.objects.filter(pk=accession_row_id).first()
                if accession_row_id
                else None
            )
            _ensure_media_for_page(
                page=page,
                accession=accession,
                accession_row=accession_row,
                reviewer=reviewer,
            )

        page.pipeline_status = SpecimenListPage.PipelineStatus.APPROVED
        page.review_status = SpecimenListPage.ReviewStatus.APPROVED
        page.reviewed_at = now_time
        page.approved_at = now_time
        page.locked_at = None
        page.assigned_reviewer = reviewer
        set_current_user(reviewer)
        try:
            page.save(
                update_fields=[
                    "pipeline_status",
                    "review_status",
                    "reviewed_at",
                    "approved_at",
                    "locked_at",
                    "assigned_reviewer",
                ]
            )
        finally:
            set_current_user(None)

    _store_page_results(page, results, reviewer)
    _move_page_image(page, reviewer)
    return results
