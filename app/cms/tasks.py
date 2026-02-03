from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import logging

from django.db import transaction

from cms.models import SpecimenListPage
from cms.ocr_processing import classify_specimen_list_page


logger = logging.getLogger(__name__)


@dataclass
class ClassificationRunSummary:
    successes: int
    failures: int
    total: int
    errors: list[str]


def _coerce_confidence(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        confidence = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if confidence < Decimal("0"):
        return Decimal("0")
    if confidence > Decimal("1"):
        return Decimal("1")
    return confidence


def _normalize_page_type(page_type: object) -> str | None:
    if not page_type:
        return None
    value = str(page_type).strip().lower()
    mapping = {
        "specimen_list_details": SpecimenListPage.PageType.SPECIMEN_LIST_DETAILS,
        "specimen_list_relations": SpecimenListPage.PageType.SPECIMEN_LIST_RELATIONS,
        "handwritten_text": SpecimenListPage.PageType.FREE_TEXT,
        "free_text": SpecimenListPage.PageType.FREE_TEXT,
        "typewritten_text": SpecimenListPage.PageType.TYPED_TEXT,
        "typed_text": SpecimenListPage.PageType.TYPED_TEXT,
        "other": SpecimenListPage.PageType.OTHER,
    }
    return mapping.get(value)


def classify_pending_specimen_pages(
    *,
    limit: int | None = None,
    ids: list[int] | None = None,
    force: bool = False,
) -> ClassificationRunSummary:
    if force:
        queryset = SpecimenListPage.objects.all().order_by("created_on", "id")
    else:
        queryset = SpecimenListPage.objects.filter(
            classification_status=SpecimenListPage.ClassificationStatus.PENDING
        ).order_by("created_on", "id")

    if ids:
        queryset = queryset.filter(id__in=ids)

    if limit:
        queryset = queryset[:limit]

    page_ids = list(queryset.values_list("id", flat=True))
    successes = 0
    failures = 0
    total = 0
    errors: list[str] = []

    for page_id in page_ids:
        total += 1
        with transaction.atomic():
            page = SpecimenListPage.objects.select_for_update().filter(id=page_id).first()
            if page is None:
                continue
            if not force and page.classification_status != SpecimenListPage.ClassificationStatus.PENDING:
                continue
            if not page.image_file:
                failures += 1
                page.classification_status = SpecimenListPage.ClassificationStatus.FAILED
                page.classification_notes = "No image file available for classification."
                page.save(update_fields=["classification_status", "classification_notes"])
                errors.append(f"page {page.id}: missing image file")
                logger.warning("Specimen list page %s missing image file", page.id)
                continue

            image_path = Path(page.image_file.path)
            if not image_path.exists():
                failures += 1
                page.classification_status = SpecimenListPage.ClassificationStatus.FAILED
                page.classification_notes = "Image file not found on disk."
                page.save(update_fields=["classification_status", "classification_notes"])
                errors.append(f"page {page.id}: image file missing")
                logger.warning("Specimen list page %s image path missing: %s", page.id, image_path)
                continue

            try:
                result = classify_specimen_list_page(image_path)
                normalized_type = _normalize_page_type(result.get("page_type"))
                if normalized_type is None:
                    raise ValueError("Unrecognized page_type from classification")
                page.page_type = normalized_type
                page.classification_status = SpecimenListPage.ClassificationStatus.CLASSIFIED
                page.classification_confidence = _coerce_confidence(result.get("confidence"))
                page.classification_notes = str(result.get("notes") or "").strip()
                page.pipeline_status = SpecimenListPage.PipelineStatus.CLASSIFIED
                page.save(
                    update_fields=[
                        "page_type",
                        "classification_status",
                        "classification_confidence",
                        "classification_notes",
                        "pipeline_status",
                    ]
                )
                successes += 1
                logger.info("Classified specimen list page %s as %s", page.id, normalized_type)
            except Exception as exc:
                failures += 1
                page.classification_status = SpecimenListPage.ClassificationStatus.FAILED
                page.classification_notes = f"Attempt failed: {exc}"
                page.save(update_fields=["classification_status", "classification_notes"])
                errors.append(f"page {page.id}: classification failed")
                logger.exception("Classification failed for specimen list page %s", page.id)

    return ClassificationRunSummary(successes=successes, failures=failures, total=total, errors=errors)
