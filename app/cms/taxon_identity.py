"""Source-independent identity for catalogue taxa."""
import re
from dataclasses import dataclass


def normalize_taxon_label(value):
    return " ".join((value or "").split())


def taxon_identity(name, rank):
    return f"{normalize_taxon_label(rank).lower()}:{normalize_taxon_label(name).lower()}"


MAX_NAME_WORDS = 3
QUALIFIER_TOKENS = {
    "cf": "cf.", "aff": "aff.", "gen": "gen.", "sp": "sp.", "spp": "spp.",
    "indet": "indet.", "nov": "nov.", "nr": "nr.", "inc": "inc.", "sed": "sed.",
    "?": "?",
}
RANK_MARKERS = {"subsp", "ssp", "var", "subspecies", "variety", "forma"}
PLACEHOLDERS = {"unknown", "unidentified", "indeterminate", "indeterminable", "none", "unnamed"}
_WORD_RE = re.compile(r"^[^\W\d_]+(?:[-'\u2019][^\W\d_]+)*$")


@dataclass(frozen=True)
class ParsedTaxonLabel:
    """Lookup-ready taxon name, with open-nomenclature qualifiers split out."""

    name: str
    qualifiers: tuple[str, ...] = ()
    valid: bool = True
    reason: str = ""


def parse_taxon_label(value) -> ParsedTaxonLabel:
    """Clean a free-text taxon label for GBIF/NOW lookup.

    Qualifiers such as ``cf.`` or ``sp.`` and rank markers such as ``subsp.``
    are removed. Names GBIF/NOW cannot match (digits, special characters,
    more than three words, placeholders) are flagged invalid.
    """
    label = normalize_taxon_label(value)
    if not label:
        return ParsedTaxonLabel("", valid=False, reason="empty name")
    if any(ch.isdigit() for ch in label):
        return ParsedTaxonLabel(label, valid=False, reason="contains numbers")

    words, phrases, phrase = [], [], []
    for token in label.replace("?", " ? ").split():
        key = token.lower().rstrip(".")
        if key in QUALIFIER_TOKENS:
            qualifier = QUALIFIER_TOKENS[key]
            if qualifier not in phrase:
                phrase.append(qualifier)
            continue
        if key == "et" and phrase:
            phrase.append("et")
            continue
        if phrase:
            phrases.append(" ".join(phrase))
            phrase = []
        if key in RANK_MARKERS or token.lower() == "f.":
            continue
        words.append(token)
    if phrase:
        phrases.append(" ".join(phrase))

    qualifiers = tuple(dict.fromkeys(phrases))
    if not words:
        return ParsedTaxonLabel("", qualifiers, False, "empty name")
    if any(not _WORD_RE.match(word) for word in words):
        return ParsedTaxonLabel(label, qualifiers, False, "contains special characters")
    if len(words) > MAX_NAME_WORDS:
        return ParsedTaxonLabel(label, qualifiers, False, f"more than {MAX_NAME_WORDS} words")
    if len(words) == 1 and words[0].lower() in PLACEHOLDERS:
        return ParsedTaxonLabel(label, qualifiers, False, "placeholder name")
    return ParsedTaxonLabel(" ".join(words), qualifiers)


def merge_qualifier(existing, additions) -> str:
    """Append qualifiers missing from ``existing`` (case-insensitive)."""
    result = (existing or "").strip()
    for addition in additions:
        pattern = r"(?<!\w)" + re.escape(addition) + r"(?!\w)"
        if not re.search(pattern, result, re.IGNORECASE):
            result = f"{result} {addition}".strip()
    return result
