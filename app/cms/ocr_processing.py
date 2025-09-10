import base64
import json
import logging
import os
import shutil
import time
import textwrap
from pathlib import Path

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
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from django.conf import settings

from .models import Media


logger = logging.getLogger(__name__)

# Load environment variables and initialize OpenAI client
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key and OpenAI else None


def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def detect_card_type(image_path: Path, model: str = "gpt-4o", timeout: int = 30, max_retries: int = 3) -> dict:
    if client is None:
        raise RuntimeError("OpenAI client is not configured")

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
- "interpreted": a normalized or searchable interpretation based on text only (e.g., standard taxon name, le=left or rt=right side, Fm=formation, Mbr=member).
- "confidence": a number from 0.0 to 1.0 estimating how confident you are in the accuracy of the "interpreted" value.

If a field is missing, set all 3 keys (`raw`, `interpreted`, `confidence`) to null. If multiple values exist for a field, use an array of objects. Use "uncertain_fields" to list any key paths that were difficult to read or ambiguous.

JSON schema:

{
  "accessions": [
    {
      "collection_abbreviation": { "raw": string|null, "interpreted": string|null, "confidence": number},      // First part of the Accession, one of "KNM", "KNMI", "KNMP". Default is "KNM" if none shown
      "specimen_prefix_abbreviation": { "raw": string|null, "interpreted": string|null, "confidence": number}, // Second part of the Accession, two capital letters. e.g., "AB", "ER"; should always be present
      "specimen_no": { "raw": integer|null, "interpreted": integer|null, "confidence": number},                // Third part of the Accession, full numeric part as written, (e.g., "1234")
      "type_status": { "raw": string|null, "interpreted": string|null, "confidence": number},                  // Usually handwritten with red (e.g., "Type", "Holotype),
      "publiched":  { "raw": string|null, "interpreted": string|null, "confidence": number},                   // is there a red forward slash on the top left corner of the card? Yes or No.
      "additional_notes": [                                                                                    // all additional extracted data from OCRa
        {
          "heading": { "raw": string|null, "interpreted": string|null, "confidence": number},                  // interpreted heading of an additional note based on the value
          "value": { "raw": string|null, "interpreted": string|null, "confidence": number},                    // the OCR:d data value
        }
      ],
      "references": [                                                                                          // zero or more full references as written on the card back side (e.g., "ref: John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
        {
          "reference_first_author": { "raw": string|null, "interpreted": string|null, "confidence": number},   // (e.g., "Harris, John M." from "John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
          "reference_year": { "raw": integer|null, "interpreted": string|null, "confidence": number},          // (e.g., "2003" from "John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
          "reference_title": , { "raw": string|null, "interpreted": string|null, "confidence": number}         // (e.g., "Lothagam: The dawn of Humanity in Eastern Africa" from "John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
          "page": { "raw": string|null, "interpreted": string|null, "confidence": number}                      // (e.g., "485-519" from "John M. Harris and Meave G. Leakey (2003) \"Lothagam: The dawn of Humanity in Eastern Africa\" Pg 485-519")
        }
      ],
      "field_slips": [
        {
          "field_number": { "raw": string|null, "interpreted": string|null, "confidence": number}              // field/collector number as written (e.g., "FS. 1035 ER. 75", "95 ER 3707", "AB 357 '95")
          "verbatim_locality": { "raw": string|null, "interpreted": string|null, "confidence": number}         // Concatenate "locality", "site", "region" etc., with a pipe "|" as written (do not infer from specimen_prefix_abbreviation, e.g. "E. Rudolf | Area 102"
          "verbatim_taxon": { "raw": string|null, "interpreted": string|null, "confidence": number}            // use identifications.verbatim_identification
          "verbatim_element": { "raw": string|null, "interpreted": string|null, "confidence": number}          // use natures.verbatim_element raw value
          "verbatim_horizon": {
            "formation": { "raw": string|null, "interpreted": string|null, "confidence": number},              // formation name as written (e.g., "Koobi Fora Formation", "Koobi Fora Fm")
            "member": { "raw": string|null, "interpreted": string|null, "confidence": number},                 // member name as written (e.g., "4m below Moiti", "Okote member")
            "bed_or_horizon": { "raw": string|null, "interpreted": string|null, "confidence": number},         // bed/horizon/tuff layer as written (e.g., "above KBS tuff", "Gray tuff member")
            "chronostratigraphy": { "raw": string|null, "interpreted": string|null, "confidence": number}      // period/epoch/age/zone as written (e.g., "Met. andrewsi zone", "Zone C")
          }
          "aerial_photo": { "raw": string|null, "interpreted": string|null, "confidence": number},             // Handwritten heading, e.g., "Photo \x1612/7", "Photo 0002"
          "verbatim_latitude": { "raw": string|null, "interpreted": string|null, "confidence": number},        // Handwritten, e.g., "Y4.9", "3°38'12 N"
          "verbatim_longitude": { "raw": string|null, "interpreted": string|null, "confidence": number},       // Handwritten, e.g., "X4.8", "36°25'30 E"
          "verbatim_elevation": { "raw": string|null, "interpreted": string|null, "confidence": number},       // Handwritten, e.g., "520 m"
        }
      ],
  "identifications": [
{
  "taxon": { "raw": string|null, "interpreted": string|null, "confidence": number},                 // interpret from the verbatim_identification, use the lowest identifiable taxon level without any qualifiers (e.g., use "Homo habilis" instead of "Homo" instead of "PRIMATES"
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
              "verbatim_element": { "raw": string|null, "interpreted": string|null, "confidence": number},     // Use raw values only. Specific bone or tooth label as written (e.g., "femur", "M1", "A: R C female B: 4 skull frags"). Assing to the right rows entry (e.g., "A: R C female B: 4 skull frags" should go to rows "A" and "B").
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
- "publiched": Yes or No
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
    if client is None:
        raise RuntimeError("OpenAI client is not configured")

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


def process_pending_scans(limit: int = 100) -> tuple[int, int, list[str]]:
    """Process up to ``limit`` scans awaiting OCR.

    Returns a tuple of ``(successes, failures, errors)`` where ``errors`` is a
    list of error descriptions for failed scans.
    """

    pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
    ocr_dir = Path(settings.MEDIA_ROOT) / "uploads" / "ocr"
    failed_dir = Path(settings.MEDIA_ROOT) / "uploads" / "failed"

    files = sorted(pending.glob("*"))[:limit]
    estimator = OCRCostEstimator()
    successes = 0
    failures = 0
    errors: list[str] = []

    for path in files:
        relative = str(path.relative_to(settings.MEDIA_ROOT))
        media = Media.objects.filter(media_location=relative).first()
        if not media:
            continue
        cost_status = estimator.scan_card()
        try:
            card_type_info = detect_card_type(path)
            card_type = card_type_info.get("card_type", "unknown")
            user_prompt = build_prompt_for_card_type(card_type)
            result = chatgpt_ocr(path, path.name, user_prompt, cost_status)
            result["card_type"] = card_type
            media.ocr_data = result
            dest = ocr_dir / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, dest)
            media.media_location.name = str(dest.relative_to(settings.MEDIA_ROOT))
            media.ocr_status = Media.OCRStatus.COMPLETED
            media.save()
            successes += 1
        except Exception as exc:
            failures += 1
            error_msg = f"{path.name}: {exc}"
            errors.append(error_msg)
            logger.exception("OCR processing failed for %s", path)
            failed_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(path, failed_dir / path.name)
            media.ocr_status = Media.OCRStatus.FAILED
            media.ocr_data = {"error": str(exc)}
            media.save()

    return successes, failures, errors

