import base64
import json
import logging
import os
import re
import shutil
import time
import textwrap
from pathlib import Path
from typing import Any, Optional

try:  # pragma: no cover - library may not be installed in tests
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(dotenv_path: str | Path | None = None) -> None:
        """Minimal .env loader used when python-dotenv isn't installed."""
        dotenv_path = Path(dotenv_path) if dotenv_path else Path(__file__).resolve().parents[2] / ".env"
        if not dotenv_path.exists():
            return
        for line in dotenv_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

try:  # pragma: no cover - library may not be installed in tests
    from openai import OpenAI, APITimeoutError
except ImportError:  # pragma: no cover
    OpenAI = None
    APITimeoutError = None  # type: ignore[assignment]

from django.conf import settings
from django.db.models import Max, Prefetch

from .models import (
    Media,
    Accession,
    Collection,
    Locality,
    Reference,
    AccessionReference,
    FieldSlip,
    AccessionFieldSlip,
    AccessionRow,
    Storage,
    InventoryStatus,
    Identification,
    NatureOfSpecimen,
    Element,
)


UNKNOWN_FIELD_NUMBER_PREFIX = "UNKNOWN FIELD NUMBER #"


class OCRTimeoutError(RuntimeError):
    """Raised when OCR processing times out after repeated attempts."""


_TIMEOUT_EXCEPTIONS: tuple[type[BaseException], ...] = (TimeoutError,)
if "APITimeoutError" in globals() and APITimeoutError is not None:  # pragma: no cover - depends on openai version
    _TIMEOUT_EXCEPTIONS = _TIMEOUT_EXCEPTIONS + (APITimeoutError,)


logger = logging.getLogger(__name__)


def _load_env() -> None:
    """Load environment variables from the project root .env file."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)


_client: Any = None


def get_openai_client() -> Any:
    """Return a configured OpenAI client or ``None`` if unavailable."""
    global _client
    if _client is not None:
        return _client

    _load_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None
    _client = OpenAI(api_key=api_key)
    return _client


def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def detect_card_type(image_path: Path, model: str = "gpt-4o", timeout: int = 30, max_retries: int = 3) -> dict:
    client = get_openai_client()
    if client is None:
        raise RuntimeError(
            "OpenAI client is not configured. Ensure OPENAI_API_KEY is set and the openai package is installed."
        )

    base64_image = encode_image_to_base64(image_path)

    detection_prompt = (
        "Please examine this card image and classify it as one of the following types:\n"
        "- `accession_card`: Used for cataloging fossil specimens with fields like Acc. No., Locality, Field No., Family, Genus, etc.\n"
        "- `field_slip`: Used in the field to record observations, often includes Field No., Collector, Locality, Horizon, and Taxon.\n"
        "- `other`: For unclear or unclassified cards.\n"
        'Return only a JSON: { "card_type": "accession_card" }'
    )

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                timeout=timeout,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that classifies card types."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": detection_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    },
                ],
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = "\n".join(
                    line for line in raw.splitlines() if not line.strip().startswith("```")
                )
            return json.loads(raw)
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def build_prompt_for_card_type(card_type: str) -> str:
    if card_type == "accession_card":
        return textwrap.dedent(
            """You are an expert OCR transcriber for handwritten museum specimen cards. The card is two-sided. The upper part is the frontside and the lower part is the backside. Read the card carefully and return ONLY a single valid JSON object (UTF-8, no trailing commas). For each field:
- "raw": the exact transcription as written (preserve all formatting, spacing, punctuation, diacritics, abbreviations). Do NOT normalize, guess, or correct.
- "interpreted": a normalized or searchable interpretation based on text only (e.g., standard taxon name, lt.=left or rt.=right side, Fm=formation, Mbr=member).
- "confidence": a number from 0.0 to 1.0 estimating how confident you are in the accuracy of the "interpreted" value.

If a field is missing, set all 3 keys (`raw`, `interpreted`, `confidence`) to null. If multiple values exist for a field, use an array of objects. Use "uncertain_fields" to list any key paths that were difficult to read or ambiguous.

Return ONLY the JSON object in this format:

JSON schema:

{
  "accessions": [
    {
      "collection_abbreviation": { "raw": string|null, "interpreted": string|null, "confidence": number},      // First part of the Accession, one of "KNM", "KNMI", "KNMP". Default is "KNM" if none shown
      "specimen_prefix_abbreviation": { "raw": string|null, "interpreted": string|null, "confidence": number}, // Second part of the Accession, two capital letters. e.g., "AB", "ER"; should always be present
      "specimen_no": { "raw": integer|null, "interpreted": integer|null, "confidence": number},                // Third part of the Accession, full numeric part as written, (e.g., "1234")
      "type_status": { "raw": string|null, "interpreted": string|null, "confidence": number},                  // Usually handwritten with red (e.g., "Type", "Holotype),
      "published":  { "raw": string|null, "interpreted": string|null, "confidence": number},                   // is there a red forward slash on the top left corner of the card? Yes or No.
      "additional_notes": [                                                                                    // all additional extracted data from OCR
        {
          "heading": { "raw": string|null, "interpreted": string|null, "confidence": number},                  // interpreted heading of an additional note based on the value
          "value": { "raw": string|null, "interpreted": string|null, "confidence": number},                    // the OCR:d data value
        }
      ],
      "references": [                                                                                          // zero or more full references as written on the card back side (e.g., "ref: John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
        {
          "reference_first_author": { "raw": string|null, "interpreted": string|null, "confidence": number},   // (e.g., "Harris, John M." from "John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
          "reference_year": { "raw": integer|null, "interpreted": string|null, "confidence": number},          // (e.g., "2003" from "John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
          "reference_title": { "raw": string|null, "interpreted": string|null, "confidence": number}         // (e.g., "Lothagam: The dawn of Humanity in Eastern Africa" from "John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
          "page": { "raw": string|null, "interpreted": string|null, "confidence": number}                      // (e.g., "485-519" from "John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
        }
      ],
      "field_slips": [
        {
          "field_number": { "raw": string|null, "interpreted": string|null, "confidence": number}              // field/collector number as written (e.g., "FS. 1035 ER. 75", "95 ER 3707", "AB 357 '95")
          "verbatim_locality": { "raw": string|null, "interpreted": string|null, "confidence": number}         // Concatenate "locality", "site", "region" etc., with a pipe "|" as written (do not infer from specimen_prefix_abbreviation, e.g. "E. Rudolf | Area 102"
          "verbatim_taxon": { "raw": string|null, "interpreted": string|null, "confidence": number}            // use identifications.verbatim_identification
          "verbatim_element": { "raw": string|null, "interpreted": string|null, "confidence": number}          // Usually found at "Nature of Specimen". Use raw values only. Specific bone or tooth label as written (e.g., "femur", "M1", "A: R C female B: 4 skull frags").
          "verbatim_horizon": {
            "formation": { "raw": string|null, "interpreted": string|null, "confidence": number},              // formation name as written (e.g., "Koobi Fora Formation", "Koobi Fora Fm")
            "member": { "raw": string|null, "interpreted": string|null, "confidence": number},                 // member name as written (e.g., "4m below Moiti", "Okote member")
            "bed_or_horizon": { "raw": string|null, "interpreted": string|null, "confidence": number},         // bed/horizon/tuff layer as written (e.g., "above KBS tuff", "Gray tuff member")
            "chronostratigraphy": { "raw": string|null, "interpreted": string|null, "confidence": number}      // period/epoch/age/zone as written (e.g., "Met. andrewsi zone", "Zone C")
          }
          "aerial_photo": { "raw": string|null, "interpreted": string|null, "confidence": number},             // Handwritten heading, e.g., "Photo 12/7", "Photo 0002"
          "verbatim_latitude": { "raw": string|null, "interpreted": string|null, "confidence": number},        // Handwritten, e.g., "Y4.9", "3°38'12 N"
          "verbatim_longitude": { "raw": string|null, "interpreted": string|null, "confidence": number},       // Handwritten, e.g., "X4.8", "36°25'30 E"
          "verbatim_elevation": { "raw": string|null, "interpreted": string|null, "confidence": number},       // Handwritten, e.g., "520 m"
        }
      ],
  "identifications": [
{
  "taxon": { "raw": string|null, "interpreted": string|null, "confidence": number},                 // interpret from the verbatim_identification, use the lowest identifiable taxon level without any qualifiers (e.g., use "Homo habilis" instead of "Homo" instead of "PRIMATES". If the lowest level is species use Genus +" "+ Species combination.
  "identification_qualifier": { "raw": string|null, "interpreted": string|null, "confidence": number}, // interpret from the verbatim_identification, (e.g., "cf.", "aff.", "sp.") if present on the name line
  "verbatim_identification": { "raw": string|null, "interpreted": string|null, "confidence": number}  // use the lowest identifiable taxon level from the taxonomic fields ("TAXON", "FAMILY", "SUB-FAMILY", "GENUS", "SPECIES")as written (may include qualifiers, subspecies, e.g., "cf. Homo habilis"). If the lowest level is species use Genus +" "+ Species combination.
  "identification_remarks": { "raw": string|null, "interpreted": string|null, "confidence": number}  // Concatenate "TAXON", "FAMILY", "SUB-FAMILY", "GENUS", "SPECIES" with a pipe "|".
}
  ],  
      "rows": [
        {
          "specimen_suffix": { "raw": string|null, "interpreted": string|null, "confidence": number},          // Fourth Part of the Accession, following the numeric part, letters (e.g., "A", "A-B", "AA", "AA-BB"). Required. Creates a new row entry. Set "-" if none shown, which is usual.
          "storage_area": { "raw": string|null, "interpreted": string|null, "confidence": number},             // storage/shelf/drawer code as written (e.g., "99 AA", "99AA", "99/AA"). Usually found within L-shaped box on top right corner of the scan and can be on two rows. Do not include nearby texts like "C'1998", "C'", "C".
          "natures": [
            {
              "element_name": { "raw": string|null, "interpreted": string|null, "confidence": number},         // interpret from the verbatim_element (e.g., "skull", "maxilla", "mandible", "tooth", "femur", "humerus")
              "side": { "raw": string|null, "interpreted": "left"|"right"|"unknown"|null, "confidence": number}, // if side is indicated (e.g., "Lt femur", "Upper Rt. m2")
              "condition": { "raw": string|null, "interpreted": string|null, "confidence": number},            // (e.g., "Damaged", "Broken", "Fragmented")
              "verbatim_element": { "raw": string|null, "interpreted": string|null, "confidence": number},     // Usually found at "Nature of Specimen". Use raw values only. Specific bone or tooth label as written (e.g., "femur", "M1", "A: R C female B: 4 skull frags"). Assing to the right rows entry (e.g., "A: R C female B: 4 skull frags" should go to rows "A" and "B").
              "portion": { "raw": string|null, "interpreted": string|null, "confidence": number},               // (e.g., "distal", "proximal", "shaft")
              "fragments": { "raw": integer|null, "interpreted": integer|null, "confidence": number},           // integer count ONLY if explicitly written, else null
            }
          ]  
        }
      ]
    }
  ]
}

Rules:
- All fields must be included, even if null.
- ignore text "P.T.O", "PTO" which means please turn over
- Ignore all texts which are strikethrough.
- "collection_abbreviation": One of "KNM", "KNMI", "KNMP". If null, use "KNM".
- The taxonomic names consists only of letters A to Z (Uppercase to Lowercase), no accents
- The suffix -IDAE is used for a family name, -INAE for a subfamily name, -INI for the name of a tribe.
- "specimen_suffix": Each specimen_suffix creates a rows entry. Default is "-". If several, (e.g., "A-C"), creates three rows with a specimen_suffix "A", "B", and "C".
- "storage_area": set the same value to all rows
- "published": Yes or No
- "reference_first_author": set the interpreted value as "surname, firstname" (i.e., "John M. Harris" would be "Harris, John M."
- "verbatim_taxon": use identifications.verbatim_identification

Return only the JSON object — no comments or explanations."""
        )
    elif card_type == "field_slip":
        return (
            "Do your best to OCR this field slip. Extract fields such as FIELD NO., COLLECTOR, DATE, LOCALITY, HORIZON, TAXON NOTES. "
            "For each field, return a structure like { \"raw\": original_value, \"interpreted\": normalized_value }. Output the result as a JSON."
        )
    else:
        return "Please OCR this card and return all recognizable fields in JSON format with raw and interpreted values."


def chatgpt_ocr(
    image_path: Path,
    image_id: str,
    user_prompt: str,
    cost_status: dict,
    model: str = "gpt-4o",
    timeout: int = 60,
    max_retries: int = 3,
) -> dict:
    client = get_openai_client()
    if client is None:
        raise RuntimeError(
            "OpenAI client is not configured. Ensure OPENAI_API_KEY is set and the openai package is installed."
        )

    base64_image = encode_image_to_base64(image_path)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                timeout=timeout,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts structured data from images."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Image ID: {image_id}\n{user_prompt}"},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    },
                ],
            )
            content = response.choices[0].message.content
            if content.strip().startswith("```"):
                content = "\n".join(
                    line for line in content.strip().splitlines() if not line.strip().startswith("```")
                )
            result = json.loads(content)
            result["cost_tracking"] = cost_status
            return result
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


class OCRCostEstimator:
    def __init__(self, budget_usd: float = 2000.0, avg_cost_per_card_usd: float = 0.01) -> None:
        self.budget = budget_usd
        self.cost_per_card = avg_cost_per_card_usd
        self.scanned = 0

    def scan_card(self) -> dict:
        self.scanned += 1
        total_cost = self.scanned * self.cost_per_card
        remaining = max(self.budget - total_cost, 0)
        return {
            "scanned_cards": self.scanned,
            "total_estimated_cost_usd": round(total_cost, 4),
            "remaining_budget_usd": round(remaining, 4),
            "cards_left": int(remaining // self.cost_per_card),
        }


def _normalise_boolean(value: object) -> bool:
    if value in (None, ""):
        return False
    return str(value).strip().lower() in {"yes", "true", "1"}


def _extract_entry_components(entry: dict) -> dict[str, object]:
    type_status = (entry.get("type_status") or {}).get("interpreted")
    published_val = (entry.get("published") or {}).get("interpreted")
    is_published = _normalise_boolean(published_val)

    notes = entry.get("additional_notes") or []
    comment_parts: list[str] = []
    for note in notes:
        heading = (note.get("heading") or {}).get("interpreted")
        value = (note.get("value") or {}).get("interpreted")
        if heading and value:
            comment_parts.append(f"{heading}: {value}")
        elif value:
            comment_parts.append(str(value))
    comment = "\n".join(comment_parts) if comment_parts else None

    references: list[dict[str, object]] = []
    for index, ref in enumerate(entry.get("references") or []):
        first_author = (ref.get("reference_first_author") or {}).get("interpreted")
        title = (ref.get("reference_title") or {}).get("interpreted")
        year = (ref.get("reference_year") or {}).get("interpreted")
        if not (first_author and title and year):
            continue
        page_val = (ref.get("page") or {}).get("interpreted")
        page = str(page_val).strip() if page_val not in (None, "") else None
        references.append(
            {
                "index": index,
                "first_author": first_author.strip(),
                "title": title.strip(),
                "year": str(year).strip(),
                "page": page,
            }
        )

    field_slips: list[dict[str, object]] = []
    for index, slip in enumerate(entry.get("field_slips") or []):
        horizon = slip.get("verbatim_horizon") or {}
        field_slips.append(
            {
                "index": index,
                "field_number": (slip.get("field_number") or {}).get("interpreted"),
                "verbatim_locality": (slip.get("verbatim_locality") or {}).get("interpreted"),
                "verbatim_taxon": (slip.get("verbatim_taxon") or {}).get("interpreted"),
                "verbatim_element": (slip.get("verbatim_element") or {}).get("interpreted"),
                "horizon_formation": (horizon.get("formation") or {}).get("interpreted"),
                "horizon_member": (horizon.get("member") or {}).get("interpreted"),
                "horizon_bed": (horizon.get("bed_or_horizon") or {}).get("interpreted"),
                "horizon_chronostratigraphy": (horizon.get("chronostratigraphy") or {}).get("interpreted"),
                "aerial_photo": (slip.get("aerial_photo") or {}).get("interpreted"),
                "verbatim_latitude": (slip.get("verbatim_latitude") or {}).get("interpreted"),
                "verbatim_longitude": (slip.get("verbatim_longitude") or {}).get("interpreted"),
                "verbatim_elevation": (slip.get("verbatim_elevation") or {}).get("interpreted"),
            }
        )

    rows: list[dict[str, object]] = []
    identifications = entry.get("identifications") or []
    for index, row in enumerate(entry.get("rows") or []):
        suffix = (row.get("specimen_suffix") or {}).get("interpreted") or "-"
        storage_name = (row.get("storage_area") or {}).get("interpreted")
        ident = identifications[index] if index < len(identifications) else {}
        ident_data = {
            "taxon": (ident.get("taxon") or {}).get("interpreted"),
            "identification_qualifier": (ident.get("identification_qualifier") or {}).get("interpreted"),
            "verbatim_identification": (ident.get("verbatim_identification") or {}).get("interpreted"),
            "identification_remarks": (ident.get("identification_remarks") or {}).get("interpreted"),
        }
        natures: list[dict[str, object]] = []
        for nature in row.get("natures") or []:
            element_name = (nature.get("element_name") or {}).get("interpreted")
            side = (nature.get("side") or {}).get("interpreted")
            condition = (nature.get("condition") or {}).get("interpreted")
            verbatim_element = (nature.get("verbatim_element") or {}).get("interpreted")
            portion = (nature.get("portion") or {}).get("interpreted")
            fragments_raw = (nature.get("fragments") or {}).get("interpreted")
            fragments = None
            if fragments_raw not in (None, ""):
                try:
                    fragments = int(fragments_raw)
                except (TypeError, ValueError):
                    fragments = None
            if not (
                element_name
                or side
                or condition
                or verbatim_element
                or portion
                or fragments is not None
            ):
                continue
            natures.append(
                {
                    "element_name": element_name,
                    "side": side,
                    "condition": condition,
                    "verbatim_element": verbatim_element,
                    "portion": portion,
                    "fragments": fragments,
                }
            )
        rows.append(
            {
                "index": index,
                "specimen_suffix": suffix,
                "storage": storage_name,
                "identification": ident_data,
                "natures": natures,
            }
        )

    return {
        "type_status": type_status,
        "is_published": is_published,
        "comment": comment,
        "references": references,
        "field_slips": field_slips,
        "rows": rows,
    }


def _make_html_key(value: str, used: set[str]) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", value or "conflict").strip("_") or "conflict"
    candidate = base
    counter = 1
    while candidate in used:
        counter += 1
        candidate = f"{base}_{counter}"
    used.add(candidate)
    return candidate


def _get_or_create_storage(area_name: str | None) -> Storage | None:
    if not area_name:
        return None
    storage = Storage.objects.filter(area__iexact=area_name).first()
    if storage:
        return storage
    parent = Storage.objects.filter(area="-Undefined").first()
    if not parent:
        parent = Storage.objects.create(area="-Undefined")
    return Storage.objects.create(area=area_name, parent_area=parent)


def _ensure_reference(first_author: str, title: str, year: str) -> Reference:
    reference = Reference.objects.filter(
        first_author__iexact=first_author.strip(),
        title__iexact=title.strip(),
        year=str(year).strip(),
    ).first()
    if reference:
        return reference
    citation = f"{first_author.strip()} ({str(year).strip()}) {title.strip()}"
    return Reference.objects.create(
        first_author=first_author.strip(),
        title=title.strip(),
        year=str(year).strip(),
        citation=citation,
    )


def _clean_string(value: object) -> str | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _has_identification_data(data: dict[str, object]) -> bool:
    if not isinstance(data, dict):
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
        value = data.get(key)
        if value not in (None, ""):
            return True
    return False


def _has_nature_data(entry: dict[str, object]) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in (
        "element_name",
        "side",
        "condition",
        "verbatim_element",
        "portion",
        "fragments",
    ):
        value = entry.get(key)
        if value not in (None, ""):
            return True
        if key == "fragments" and value in (0, "0"):
            return True
    return False


def _has_any_nature_data(entries: list[dict[str, object]]) -> bool:
    for entry in entries or []:
        if _has_nature_data(entry):
            return True
    return False


def _generate_unknown_field_number() -> str:
    count = FieldSlip.objects.filter(
        field_number__startswith=UNKNOWN_FIELD_NUMBER_PREFIX
    ).count()
    next_number = count + 1
    candidate = f"{UNKNOWN_FIELD_NUMBER_PREFIX}{next_number}"
    while FieldSlip.objects.filter(field_number=candidate).exists():
        next_number += 1
        candidate = f"{UNKNOWN_FIELD_NUMBER_PREFIX}{next_number}"
    return candidate


def _ensure_field_slip(data: dict[str, object]) -> FieldSlip | None:
    field_number = _clean_string(data.get("field_number"))
    verb_locality = _clean_string(data.get("verbatim_locality"))
    verb_taxon = _clean_string(data.get("verbatim_taxon"))
    if not verb_taxon:
        return None

    verbatim_element = _clean_string(data.get("verbatim_element"))
    if not verbatim_element:
        return None

    aerial_photo = _clean_string(data.get("aerial_photo"))
    verbatim_latitude = _clean_string(data.get("verbatim_latitude"))
    verbatim_longitude = _clean_string(data.get("verbatim_longitude"))
    verbatim_elevation = _clean_string(data.get("verbatim_elevation"))

    base_queryset = FieldSlip.objects.filter(
        verbatim_locality=verb_locality,
        verbatim_taxon=verb_taxon,
        verbatim_element=verbatim_element,
    )
    if field_number:
        field_slip = base_queryset.filter(field_number=field_number).first()
        if field_slip:
            return field_slip
    else:
        field_slip = base_queryset.filter(
            field_number__startswith=UNKNOWN_FIELD_NUMBER_PREFIX
        ).first()
        if field_slip:
            return field_slip
        field_number = _generate_unknown_field_number()

    horizon_parts: list[str] = []
    for key in (
        "horizon_formation",
        "horizon_member",
        "horizon_bed",
        "horizon_chronostratigraphy",
    ):
        value = _clean_string(data.get(key))
        if value:
            horizon_parts.append(str(value))
    horizon = " | ".join(horizon_parts) if horizon_parts else None

    return FieldSlip.objects.create(
        field_number=field_number,
        verbatim_locality=verb_locality,
        verbatim_taxon=verb_taxon,
        verbatim_element=verbatim_element,
        verbatim_horizon=horizon,
        aerial_photo=aerial_photo,
        verbatim_latitude=verbatim_latitude,
        verbatim_longitude=verbatim_longitude,
        verbatim_elevation=verbatim_elevation,
    )


def _apply_references(
    accession: Accession,
    references: list[dict[str, object]],
    selection: set[int] | None = None,
) -> None:
    for reference in references:
        index = int(reference.get("index", 0))
        if selection is not None and index not in selection:
            continue
        first_author = reference.get("first_author")
        title = reference.get("title")
        year = reference.get("year")
        if not (first_author and title and year):
            continue
        reference_obj = _ensure_reference(str(first_author), str(title), str(year))
        page = reference.get("page")
        AccessionReference.objects.update_or_create(
            accession=accession,
            reference=reference_obj,
            defaults={"page": page if page not in (None, "") else None},
        )


def _apply_field_slips(
    accession: Accession,
    field_slips: list[dict[str, object]],
    selection: set[int] | None = None,
) -> None:
    for entry in field_slips:
        index = int(entry.get("index", 0))
        if selection is not None and index not in selection:
            continue
        field_slip = _ensure_field_slip(entry)
        if not field_slip:
            continue
        AccessionFieldSlip.objects.get_or_create(accession=accession, fieldslip=field_slip)


def _apply_rows(
    accession: Accession,
    rows: list[dict[str, object]],
    selection: set[str] | None = None,
) -> None:
    last_ident_data: dict[str, object] | None = None
    last_natures_data: list[dict[str, object]] = []

    for row in rows:
        suffix = row.get("specimen_suffix") or "-"
        if selection is not None and suffix not in selection:
            continue
        storage_name = row.get("storage")
        storage_obj = _get_or_create_storage(str(storage_name)) if storage_name else None
        defaults = {
            "storage": storage_obj,
            "status": InventoryStatus.UNKNOWN,
        }
        row_obj, created = AccessionRow.objects.get_or_create(
            accession=accession,
            specimen_suffix=suffix,
            defaults=defaults,
        )
        if not created and storage_obj and row_obj.storage != storage_obj:
            row_obj.storage = storage_obj
            row_obj.save(update_fields=["storage"])

        row_obj.identification_set.all().delete()
        row_obj.natureofspecimen_set.all().delete()

        ident = row.get("identification") or {}
        if _has_identification_data(ident):
            last_ident_data = ident
            ident_to_apply = ident
        elif last_ident_data:
            ident_to_apply = last_ident_data
        else:
            ident_to_apply = {}

        if _has_identification_data(ident_to_apply):
            Identification.objects.create(
                accession_row=row_obj,
                taxon=ident_to_apply.get("taxon"),
                identification_qualifier=ident_to_apply.get("identification_qualifier"),
                verbatim_identification=ident_to_apply.get("verbatim_identification"),
                identification_remarks=ident_to_apply.get("identification_remarks"),
            )

        natures = row.get("natures") or []
        if _has_any_nature_data(natures):
            last_natures_data = natures
            natures_to_apply = natures
        elif last_natures_data:
            natures_to_apply = last_natures_data
        else:
            natures_to_apply = []

        for nature in natures_to_apply:
            element_name = _clean_string(nature.get("element_name"))
            verbatim_element = _clean_string(nature.get("verbatim_element"))
            resolved_name = element_name or verbatim_element
            element = None
            if resolved_name:
                element = Element.objects.filter(name=resolved_name).first()
            parent = Element.objects.filter(name="-Undefined").first()
            if element is None:
                if parent is None:
                    parent = Element.objects.create(name="-Undefined")
                if not resolved_name or resolved_name == parent.name:
                    element = parent
                    resolved_name = parent.name
                else:
                    element = Element.objects.create(
                        name=resolved_name,
                        parent_element=parent,
                    )
            nature["element_name"] = resolved_name
            fragments = nature.get("fragments")
            if fragments in (None, ""):
                fragments_value = 0
            else:
                try:
                    fragments_value = int(fragments)
                except (TypeError, ValueError):
                    fragments_value = 0
            NatureOfSpecimen.objects.create(
                accession_row=row_obj,
                element=element,
                side=nature.get("side"),
                condition=nature.get("condition"),
                verbatim_element=nature.get("verbatim_element"),
                portion=nature.get("portion"),
                fragments=fragments_value,
            )


def _serialize_accession(accession: Accession) -> dict[str, object]:
    accession = (
        Accession.objects.filter(pk=accession.pk)
        .select_related("collection", "specimen_prefix")
        .prefetch_related(
            Prefetch(
                "accessionrow_set",
                queryset=AccessionRow.objects.select_related("storage")
                .prefetch_related(
                    Prefetch("identification_set", queryset=Identification.objects.select_related("reference")),
                    Prefetch("natureofspecimen_set", queryset=NatureOfSpecimen.objects.select_related("element")),
                )
                .order_by("specimen_suffix"),
            ),
            Prefetch(
                "accessionreference_set",
                queryset=AccessionReference.objects.select_related("reference"),
            ),
            Prefetch(
                "fieldslip_links",
                queryset=AccessionFieldSlip.objects.select_related("fieldslip"),
            ),
        )
        .first()
    )
    if accession is None:
        return {}

    rows: list[dict[str, object]] = []
    for row in accession.accessionrow_set.all():
        ident = row.identification_set.first()
        ident_data = {
            "taxon": getattr(ident, "taxon", None),
            "identification_qualifier": getattr(ident, "identification_qualifier", None),
            "verbatim_identification": getattr(ident, "verbatim_identification", None),
            "identification_remarks": getattr(ident, "identification_remarks", None),
        }
        natures: list[dict[str, object]] = []
        for nature in row.natureofspecimen_set.all():
            natures.append(
                {
                    "element_name": nature.element.name if nature.element else None,
                    "side": nature.side,
                    "condition": nature.condition,
                    "verbatim_element": nature.verbatim_element,
                    "portion": nature.portion,
                    "fragments": nature.fragments,
                }
            )
        rows.append(
            {
                "specimen_suffix": row.specimen_suffix,
                "storage": row.storage.area if row.storage else None,
                "identification": ident_data,
                "natures": natures,
            }
        )

    references: list[dict[str, object]] = []
    for link in accession.accessionreference_set.all():
        ref = link.reference
        references.append(
            {
                "first_author": getattr(ref, "first_author", None),
                "title": getattr(ref, "title", None),
                "year": getattr(ref, "year", None),
                "page": link.page,
            }
        )

    field_slips: list[dict[str, object]] = []
    for link in accession.fieldslip_links.all():
        slip = link.fieldslip
        field_slips.append(
            {
                "field_number": getattr(slip, "field_number", None),
                "verbatim_locality": getattr(slip, "verbatim_locality", None),
                "verbatim_taxon": getattr(slip, "verbatim_taxon", None),
                "verbatim_element": getattr(slip, "verbatim_element", None),
                "verbatim_horizon": getattr(slip, "verbatim_horizon", None),
                "aerial_photo": getattr(slip, "aerial_photo", None),
                "verbatim_latitude": getattr(slip, "verbatim_latitude", None),
                "verbatim_longitude": getattr(slip, "verbatim_longitude", None),
                "verbatim_elevation": getattr(slip, "verbatim_elevation", None),
            }
        )

    return {
        "type_status": accession.type_status,
        "comment": accession.comment,
        "is_published": accession.is_published,
        "rows": rows,
        "references": references,
        "field_slips": field_slips,
    }


def _build_conflict_detail(
    key: str,
    collection: Collection,
    specimen_prefix: Locality,
    specimen_no: int,
    existing_qs,
    components: dict[str, object],
) -> dict[str, object]:
    existing_entries: list[dict[str, object]] = []
    for accession in existing_qs:
        existing_entries.append(
            {
                "id": accession.pk,
                "instance_number": accession.instance_number,
                "label": str(accession),
                "data": _serialize_accession(accession),
            }
        )

    existing_snapshot = existing_entries[0]["data"] if existing_entries else {}

    rows: list[dict[str, object]] = []
    used_suffixes: set[str] = set()
    for row in components.get("rows", []):
        row_copy = {**row}
        row_copy["identification"] = dict(row.get("identification") or {})
        row_copy["natures"] = [dict(nature) for nature in row.get("natures") or []]
        html_suffix = _make_html_key(str(row_copy.get("specimen_suffix") or "row"), used_suffixes)
        row_copy["html_suffix"] = html_suffix
        existing_row = None
        for candidate in existing_snapshot.get("rows", []):
            if candidate.get("specimen_suffix") == row_copy.get("specimen_suffix"):
                existing_row = candidate
                break
        row_copy["existing"] = existing_row
        rows.append(row_copy)

    references = [dict(ref) for ref in components.get("references", [])]
    field_slips = [dict(slip) for slip in components.get("field_slips", [])]

    max_instance = existing_qs.aggregate(Max("instance_number")).get("instance_number__max") or 1

    proposed = dict(components)
    proposed["rows"] = rows
    proposed["references"] = references
    proposed["field_slips"] = field_slips

    return {
        "key": key,
        "collection": collection.abbreviation,
        "specimen_prefix": specimen_prefix.abbreviation,
        "specimen_no": specimen_no,
        "reason": "Existing accession detected",
        "message": "Existing accession detected. Choose whether to create a new instance or update the existing record.",
        "existing_accessions": existing_entries,
        "existing_snapshot": existing_snapshot,
        "proposed": proposed,
        "next_instance": max_instance + 1,
    }


def describe_accession_conflicts(media: Media) -> list[dict[str, object]]:
    data = dict(media.ocr_data or {})
    if data.get("card_type") != "accession_card":
        return []

    accessions = data.get("accessions") or []
    processed_records = data.get("_processed_accessions") or []
    processed_keys = {rec.get("key") for rec in processed_records if rec.get("key")}

    conflicts: list[dict[str, object]] = []
    used_html_keys: set[str] = set()

    for entry in accessions:
        raw_coll_abbr = (entry.get("collection_abbreviation") or {}).get("interpreted")
        coll_abbr = raw_coll_abbr or "KNM"
        collection = Collection.objects.filter(abbreviation=coll_abbr).first()
        if not collection and coll_abbr != "KNM":
            collection = Collection.objects.filter(abbreviation="KNM").first()
        if not collection:
            continue

        prefix_abbr = (entry.get("specimen_prefix_abbreviation") or {}).get("interpreted")
        if not prefix_abbr:
            continue
        specimen_prefix = Locality.objects.filter(abbreviation=prefix_abbr).first()
        if not specimen_prefix:
            continue

        specimen_no_value = (entry.get("specimen_no") or {}).get("interpreted")
        try:
            specimen_no = int(specimen_no_value)
        except (TypeError, ValueError):
            continue

        key = f"{collection.abbreviation}:{specimen_prefix.abbreviation}:{specimen_no}"
        if key in processed_keys:
            continue

        existing_qs = Accession.objects.filter(
            collection=collection,
            specimen_prefix=specimen_prefix,
            specimen_no=specimen_no,
        ).order_by("instance_number")
        if not existing_qs.exists():
            continue

        components = _extract_entry_components(entry)
        conflict = _build_conflict_detail(
            key,
            collection,
            specimen_prefix,
            specimen_no,
            existing_qs,
            components,
        )
        conflict["html_key"] = _make_html_key(key, used_html_keys)
        conflicts.append(conflict)

    return conflicts


def create_accessions_from_media(
    media: Media,
    resolution_map: dict[str, dict[str, object]] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Create :class:`Accession` objects from a media's OCR data.

    The OCR payload is expected to be stored on ``media.ocr_data``. When the
    detected ``card_type`` is ``accession_card`` the data is used to create one
    or more :class:`Accession` records. The function is idempotent: accessions
    that have already been created for this media are remembered inside the OCR
    JSON (under ``_processed_accessions``) and are not recreated on subsequent
    calls. If an accession would collide with an existing record, the conflict
    is reported and the accession is not created unless a resolution is
    provided.
    """

    data = dict(media.ocr_data or {})
    if data.get("card_type") != "accession_card":
        return {"created": [], "conflicts": []}

    resolution_map = resolution_map or {}
    accessions = data.get("accessions") or []
    processed_records = data.get("_processed_accessions") or []
    processed_map = {rec.get("key"): rec for rec in processed_records if rec.get("key")}
    updated_records = [dict(rec) for rec in processed_records]
    created_records: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    first_accession: Optional[Accession] = None

    for entry in accessions:
        raw_coll_abbr = (entry.get("collection_abbreviation") or {}).get("interpreted")
        coll_abbr = raw_coll_abbr or "KNM"
        collection = Collection.objects.filter(abbreviation=coll_abbr).first()
        if not collection and coll_abbr != "KNM":
            collection = Collection.objects.filter(abbreviation="KNM").first()
        if not collection:
            conflicts.append({"key": coll_abbr, "reason": "Collection not found"})
            continue

        prefix_abbr = (entry.get("specimen_prefix_abbreviation") or {}).get("interpreted")
        if not prefix_abbr:
            conflicts.append(
                {
                    "key": f"{collection.abbreviation}:<missing>",
                    "reason": "Specimen prefix missing",
                }
            )
            continue
        specimen_prefix = Locality.objects.filter(abbreviation=prefix_abbr).first()
        if not specimen_prefix:
            specimen_prefix = Locality.objects.create(
                abbreviation=prefix_abbr,
                name=f"Temporary Locality {prefix_abbr}",
            )

        specimen_no_value = (entry.get("specimen_no") or {}).get("interpreted")
        if specimen_no_value in (None, ""):
            conflicts.append(
                {
                    "key": f"{collection.abbreviation}:{prefix_abbr}",
                    "reason": "Specimen number missing",
                }
            )
            continue
        try:
            specimen_no = int(specimen_no_value)
        except (TypeError, ValueError):
            conflicts.append(
                {
                    "key": f"{collection.abbreviation}:{prefix_abbr}",
                    "reason": f"Invalid specimen number: {specimen_no_value}",
                }
            )
            continue

        key = f"{collection.abbreviation}:{specimen_prefix.abbreviation}:{specimen_no}"
        processed_entry = processed_map.get(key)
        if processed_entry:
            accession_id = processed_entry.get("accession_id")
            accession = Accession.objects.filter(pk=accession_id).first()
            if accession is None:
                conflicts.append(
                    {
                        "key": key,
                        "reason": "Previously created accession is missing",
                        "accession_id": accession_id,
                    }
                )
            else:
                if first_accession is None:
                    first_accession = accession
            continue

        components = _extract_entry_components(entry)

        existing_qs = Accession.objects.filter(
            collection=collection,
            specimen_prefix=specimen_prefix,
            specimen_no=specimen_no,
        ).order_by("instance_number")

        resolution_entry = resolution_map.get(key)

        if existing_qs.exists():
            if not resolution_entry:
                conflict = _build_conflict_detail(
                    key,
                    collection,
                    specimen_prefix,
                    specimen_no,
                    existing_qs,
                    components,
                )
                conflicts.append(conflict)
                continue

            action = resolution_entry.get("action")
            if action == "new_instance":
                max_instance = (
                    existing_qs.aggregate(Max("instance_number")).get("instance_number__max") or 1
                )
                instance_number = resolution_entry.get("instance_number")
                try:
                    instance_number_int = int(instance_number) if instance_number is not None else None
                except (TypeError, ValueError):
                    instance_number_int = None
                next_instance = instance_number_int if instance_number_int and instance_number_int > max_instance else max_instance + 1
                accession = Accession.objects.create(
                    collection=collection,
                    specimen_prefix=specimen_prefix,
                    specimen_no=specimen_no,
                    instance_number=next_instance,
                    type_status=components.get("type_status"),
                    is_published=components.get("is_published", False),
                    comment=components.get("comment"),
                )
                _apply_references(accession, components.get("references", []))
                _apply_field_slips(accession, components.get("field_slips", []))
                _apply_rows(accession, components.get("rows", []))
            elif action == "update_existing":
                accession = existing_qs.filter(pk=resolution_entry.get("accession_id")).first() or existing_qs.first()
                fields = resolution_entry.get("fields") or {}
                update_fields: list[str] = []
                if "type_status" in fields:
                    accession.type_status = fields["type_status"]
                    update_fields.append("type_status")
                if "comment" in fields:
                    accession.comment = fields["comment"]
                    update_fields.append("comment")
                if update_fields:
                    accession.save(update_fields=update_fields)

                reference_selection = {
                    int(idx)
                    for idx in resolution_entry.get("references", [])
                    if isinstance(idx, (int, str)) and str(idx).isdigit()
                }
                if reference_selection:
                    _apply_references(accession, components.get("references", []), reference_selection)

                field_slip_selection = {
                    int(idx)
                    for idx in resolution_entry.get("field_slips", [])
                    if isinstance(idx, (int, str)) and str(idx).isdigit()
                }
                if field_slip_selection:
                    _apply_field_slips(accession, components.get("field_slips", []), field_slip_selection)

                row_selection = {
                    str(suffix)
                    for suffix in resolution_entry.get("rows", [])
                    if suffix not in (None, "")
                }
                if row_selection:
                    _apply_rows(accession, components.get("rows", []), row_selection)

                record = {
                    "key": key,
                    "accession_id": accession.pk,
                    "collection": collection.abbreviation,
                    "specimen_prefix": specimen_prefix.abbreviation,
                    "specimen_no": specimen_no,
                    "instance_number": accession.instance_number,
                    "accession": str(accession),
                }
                processed_map[key] = record
                updated_records.append(record)
                if first_accession is None:
                    first_accession = accession
                continue
            else:
                conflict = _build_conflict_detail(
                    key,
                    collection,
                    specimen_prefix,
                    specimen_no,
                    existing_qs,
                    components,
                )
                conflict["reason"] = "Resolution not recognised"
                conflicts.append(conflict)
                continue
        else:
            accession = Accession.objects.create(
                collection=collection,
                specimen_prefix=specimen_prefix,
                specimen_no=specimen_no,
                instance_number=1,
                type_status=components.get("type_status"),
                is_published=components.get("is_published", False),
                comment=components.get("comment"),
            )
            _apply_references(accession, components.get("references", []))
            _apply_field_slips(accession, components.get("field_slips", []))
            _apply_rows(accession, components.get("rows", []))

        if first_accession is None:
            first_accession = accession
        record = {
            "key": key,
            "accession_id": accession.pk,
            "collection": collection.abbreviation,
            "specimen_prefix": specimen_prefix.abbreviation,
            "specimen_no": specimen_no,
            "instance_number": accession.instance_number,
            "accession": str(accession),
        }
        created_records.append(record)
        processed_map[key] = record
        updated_records.append(record)

    if first_accession is None:
        for record in updated_records:
            accession_id = record.get("accession_id")
            if accession_id:
                accession = Accession.objects.filter(pk=accession_id).first()
                if accession:
                    first_accession = accession
                    break

    updates: list[str] = []
    if first_accession and media.accession_id != first_accession.pk:
        media.accession = first_accession
        updates.append("accession")
    if updated_records != processed_records:
        data["_processed_accessions"] = updated_records
        media.ocr_data = data
        updates.append("ocr_data")
    if updates:
        media.save(update_fields=updates)

    return {"created": created_records, "conflicts": conflicts}


def _mark_scan_failed(media: Media, path: Path, failed_dir: Path, exc: Exception | str) -> None:
    """Move ``path`` to the failed directory and persist failure metadata."""

    failed_dir.mkdir(parents=True, exist_ok=True)
    dest = failed_dir / path.name
    if path.exists():  # Guard against situations where the file was already moved.
        shutil.move(path, dest)
    media.media_location.name = str(dest.relative_to(settings.MEDIA_ROOT))
    media.ocr_status = Media.OCRStatus.FAILED
    media.ocr_data = {"error": str(exc)}
    media.save(update_fields=["media_location", "ocr_status", "ocr_data"])


def _process_single_scan(
    media: Media,
    path: Path,
    estimator: "OCRCostEstimator",
    ocr_dir: Path,
    *,
    max_attempts: int = 3,
) -> None:
    """Run OCR for a single pending scan, retrying on timeouts."""

    cost_status = estimator.scan_card()
    last_timeout: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            card_type_info = detect_card_type(path)
            card_type = card_type_info.get("card_type", "unknown")
            user_prompt = build_prompt_for_card_type(card_type)
            result = chatgpt_ocr(path, path.name, user_prompt, cost_status)
            result["card_type"] = card_type
            dest = ocr_dir / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, dest)
            media.media_location.name = str(dest.relative_to(settings.MEDIA_ROOT))
            media.ocr_data = result
            media.ocr_status = Media.OCRStatus.COMPLETED
            media.qc_status = Media.QCStatus.PENDING_INTERN
            media.save(update_fields=["ocr_data", "media_location", "ocr_status", "qc_status"])
            return
        except _TIMEOUT_EXCEPTIONS as exc:  # type: ignore[arg-type]
            last_timeout = exc
            logger.warning(
                "OCR attempt %s/%s timed out for %s", attempt, max_attempts, path.name
            )
            if attempt == max_attempts:
                raise OCRTimeoutError(str(exc)) from exc
            time.sleep(2 ** (attempt - 1))
        except Exception:
            raise

    if last_timeout is not None:
        raise OCRTimeoutError(str(last_timeout))


def process_pending_scans(limit: int = 1) -> tuple[int, int, int, list[str], Optional[str]]:
    """Process up to ``limit`` scans awaiting OCR.

    Returns a tuple of ``(successes, failures, total, errors, jammed_filename)``
    where ``total`` is the number of scans considered and ``errors`` is a list
    of error descriptions for failed scans. ``jammed_filename`` will be set if
    OCR was halted early because a scan repeatedly timed out.
    """

    pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
    ocr_dir = Path(settings.MEDIA_ROOT) / "uploads" / "ocr"
    failed_dir = Path(settings.MEDIA_ROOT) / "uploads" / "failed"

    files = sorted(pending.glob("*"))
    estimator = OCRCostEstimator()
    successes = 0
    failures = 0
    total = 0
    errors: list[str] = []
    jammed_filename: Optional[str] = None

    for path in files:
        if limit is not None and total >= limit:
            break

        relative = str(path.relative_to(settings.MEDIA_ROOT))
        media = Media.objects.filter(media_location=relative).first()
        if not media:
            continue

        total += 1

        try:
            _process_single_scan(media, path, estimator, ocr_dir)
            successes += 1
        except OCRTimeoutError as exc:
            failures += 1
            error_msg = f"{path.name}: {exc}"
            errors.append(error_msg)
            jammed_filename = path.name
            logger.error("OCR timed out for %s after multiple attempts", path, exc_info=True)
            _mark_scan_failed(media, path, failed_dir, exc)
            break
        except Exception as exc:
            failures += 1
            error_msg = f"{path.name}: {exc}"
            errors.append(error_msg)
            logger.exception("OCR processing failed for %s", path)
            _mark_scan_failed(media, path, failed_dir, exc)

    return successes, failures, total, errors, jammed_filename
