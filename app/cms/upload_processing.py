import hashlib
import logging
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import close_old_connections

from .models import Media, SpecimenListPDF, SpecimenListPage
from . import scanning_utils

logger = logging.getLogger("cms.upload_processing")

INCOMING = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
PENDING = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
MANUAL_QC = Path(settings.MEDIA_ROOT) / "uploads" / "manual_qc"
REJECTED = Path(settings.MEDIA_ROOT) / "uploads" / "rejected"

TIMESTAMP_FORMAT = "%Y-%m-%dT%H%M%S"
NAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}\.png$", re.IGNORECASE)
MANUAL_QC_PATTERN = re.compile(r"^\d+\.jpe?g$", re.IGNORECASE)
SPECIMEN_LIST_DPI = getattr(settings, "SPECIMEN_LIST_DPI", 300)


def create_media(
    path: Path, *, scan_timestamp: datetime
) -> None:
    """Create a Media record for a newly accepted scan."""
    logger.info(
        "Processing uploaded media %s with filename timestamp %s",
        path,
        scan_timestamp.isoformat(),
    )
    created = scanning_utils.to_nairobi(scan_timestamp)
    scanning_utils.auto_complete_scans()
    scan = scanning_utils.find_scan_for_timestamp(created)
    if scan:
        logger.info(
            "Matched media %s to scanning #%s (%s -> %s) using Nairobi timestamp %s",
            path,
            scan.pk,
            scan.start_time,
            scan.end_time,
            created.isoformat(),
        )
    else:
        logger.warning(
            "No scanning found for media %s using Nairobi timestamp %s",
            path,
            created.isoformat(),
        )
    media = Media(
        type="photo",
        license="CC0",
        rights_holder="National Museums of Kenya",
        scanning=scan,
    )
    media.media_location.name = str(path.relative_to(settings.MEDIA_ROOT))
    media.save()


def create_manual_qc_media(path: Path) -> None:
    """Create a Media record for a manual QC scan upload."""

    logger.info("Processing manual QC media %s", path)
    media = Media(
        type="photo",
        license="CC0",
        rights_holder="National Museums of Kenya",
    )
    media.media_location.name = str(path.relative_to(settings.MEDIA_ROOT))
    media.save()


def process_file(src: Path) -> Path:
    """Validate ``src`` and move it to ``pending`` or ``rejected``.

    Returns the destination path after moving. Creates a ``Media`` row for
    valid files.
    """
    if NAME_PATTERN.match(src.name):
        dest = PENDING / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.strptime(src.stem, TIMESTAMP_FORMAT)
        timestamp = timestamp.replace(tzinfo=scanning_utils.NAIROBI_TZ)
        shutil.move(src, dest)
        create_media(dest, scan_timestamp=timestamp)
    elif MANUAL_QC_PATTERN.match(src.name):
        dest = MANUAL_QC / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
        create_manual_qc_media(dest)
    else:
        dest = REJECTED / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
    return dest


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_pdf_page_count(pdf_path: Path) -> int:
    command = ["pdfinfo", str(pdf_path)]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.lower().startswith("pages:"):
            value = line.split(":", 1)[1].strip()
            return int(value)
    raise RuntimeError("Unable to determine PDF page count via pdfinfo.")


def _split_pdf_page_to_image(
    pdf_path: Path, output_dir: Path, dpi: int, page_number: int
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "page"
    command = [
        "pdftoppm",
        "-png",
        "-r",
        str(dpi),
        "-f",
        str(page_number),
        "-l",
        str(page_number),
        str(pdf_path),
        str(prefix),
    ]
    subprocess.run(command, check=True)
    expected_name = f"page-{page_number}.png"
    matches = list(output_dir.glob("page-*.png"))
    if not matches:
        raise RuntimeError(
            f"Expected page image not found for page {page_number}."
        )
    matches.sort()
    image = matches[0]
    renamed_path = output_dir / f"page_{page_number:03d}.png"
    image.rename(renamed_path)
    return renamed_path


def queue_specimen_list_processing(pdf_id: int) -> None:
    if not getattr(settings, "SPECIMEN_LIST_PROCESS_ASYNC", False):
        logger.info(
            "Specimen list PDF %s queued for offline processing.", pdf_id
        )
        return
    thread = threading.Thread(
        target=process_specimen_list_pdf,
        args=(pdf_id,),
        name=f"specimen-list-{pdf_id}",
        daemon=True,
    )
    thread.start()


def process_specimen_list_pdf(pdf_id: int) -> None:
    close_old_connections()
    try:
        pdf = SpecimenListPDF.objects.get(pk=pdf_id)
    except SpecimenListPDF.DoesNotExist:
        logger.warning("Specimen list PDF %s not found for processing.", pdf_id)
        return

    pdf.status = SpecimenListPDF.Status.PROCESSING
    pdf.save(update_fields=["status"])

    if not pdf.stored_file:
        pdf.status = SpecimenListPDF.Status.ERROR
        pdf.save(update_fields=["status"])
        logger.error("Specimen list PDF %s missing stored file.", pdf_id)
        return

    try:
        pdf_path = Path(pdf.stored_file.path)
    except Exception as exc:  # pragma: no cover - storage backends may not expose paths
        pdf.status = SpecimenListPDF.Status.ERROR
        pdf.save(update_fields=["status"])
        logger.exception("Specimen list PDF %s missing file path: %s", pdf_id, exc)
        return

    try:
        pdf.sha256 = _compute_sha256(pdf_path)
        pdf.save(update_fields=["sha256"])
    except Exception as exc:  # pragma: no cover - filesystem errors
        logger.exception("Failed to compute sha256 for PDF %s: %s", pdf_id, exc)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            page_total = _get_pdf_page_count(pdf_path)

            if pdf.pages.exists():
                pdf.pages.all().delete()

            pages: list[SpecimenListPage] = []
            for page_number in range(1, page_total + 1):
                image_path = _split_pdf_page_to_image(
                    pdf_path,
                    output_dir,
                    dpi=SPECIMEN_LIST_DPI,
                    page_number=page_number,
                )
                page = SpecimenListPage(pdf=pdf, page_number=page_number)
                with image_path.open("rb") as handle:
                    page.image_file.save(image_path.name, File(handle), save=False)
                page.save()
                pages.append(page)

            pdf.page_count = len(pages)
            pdf.status = SpecimenListPDF.Status.SPLIT
            pdf.save(update_fields=["page_count", "status"])
    except Exception as exc:
        logger.exception("Failed to split specimen list PDF %s: %s", pdf_id, exc)
        pdf.status = SpecimenListPDF.Status.ERROR
        pdf.save(update_fields=["status"])
