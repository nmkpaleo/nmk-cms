"""NOW taxonomy synchronization service layer."""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import (
    Taxon,
    TaxonExternalSource,
    TaxonStatus,
    TaxonomyImport,
)

logger = logging.getLogger(__name__)

HttpGetter = Callable[[str], requests.Response]


TAXONOMY_FIELDS = [
    "kingdom",
    "phylum",
    "class_name",
    "order",
    "superfamily",
    "family",
    "subfamily",
    "tribe",
    "genus",
    "species",
    "infraspecific_epithet",
]

TAXONOMY_DEFAULTS = {
    "kingdom": "Animalia",
    "phylum": "Chordata",
    "class_name": "Mammalia",
}

RANK_TO_FIELD = {
    "order": "order",
    "superfamily": "superfamily",
    "family": "family",
    "subfamily": "subfamily",
    "tribe": "tribe",
    "genus": "genus",
    "species": "species",
    "subspecies": "infraspecific_epithet",
}

RANK_SCOPE = {
    "order": ["order"],
    "superfamily": ["order", "superfamily"],
    "family": ["order", "superfamily", "family"],
    "subfamily": ["order", "superfamily", "family", "subfamily"],
    "tribe": ["order", "superfamily", "family", "subfamily", "tribe"],
    "genus": ["order", "superfamily", "family", "subfamily", "tribe", "genus"],
    "species": ["order", "superfamily", "family", "subfamily", "tribe", "genus", "species"],
    "subspecies": [
        "order",
        "superfamily",
        "family",
        "subfamily",
        "tribe",
        "genus",
        "species",
        "infraspecific_epithet",
    ],
}

TAXONOMY_ALIASES = {
    "class_name": ["class", "class_name", "class1", "classlevel"],
    "order": ["order", "order_name", "taxon_order"],
    "superfamily": ["superfamily", "superfamily_name"],
    "family": ["family", "family_name"],
    "subfamily": ["subfamily", "subfamily_name"],
    "tribe": ["tribe", "tribe_name"],
    "genus": ["genus", "genus_name"],
    "species": ["species", "species_name", "species_epithet"],
    "infraspecific_epithet": ["subspecies", "infraspecific_epithet", "varietas"],
}

SKIPPED_RANKS = {"subclass", "suborder"}


@dataclass(frozen=True)
class AcceptedRecord:
    """Parsed representation of an accepted NOW taxon."""

    external_id: str
    name: str
    rank: str
    author_year: str
    source_version: str
    taxonomy: Dict[str, str]


@dataclass(frozen=True)
class SynonymRecord:
    """Parsed representation of a NOW synonym taxon."""

    external_id: str
    name: str
    accepted_name: str
    accepted_external_id: str
    rank: str
    author_year: str
    source_version: str
    taxonomy: Dict[str, str]


@dataclass(frozen=True)
class SyncIssue:
    code: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AcceptedUpdate:
    instance: Taxon
    record: AcceptedRecord
    changes: Dict[str, Any]


@dataclass
class SynonymUpdate:
    instance: Taxon
    record: SynonymRecord
    changes: Dict[str, Any]


@dataclass
class SyncPreview:
    accepted_to_create: List[AcceptedRecord]
    accepted_to_update: List[AcceptedUpdate]
    synonyms_to_create: List[SynonymRecord]
    synonyms_to_update: List[SynonymUpdate]
    to_deactivate: List[Taxon]
    issues: List[SyncIssue]
    source_version: str

    @property
    def counts(self) -> Dict[str, Any]:
        created_total = len(self.accepted_to_create) + len(self.synonyms_to_create)
        updated_total = len(self.accepted_to_update) + len(self.synonyms_to_update)
        synonym_links = len(self.synonyms_to_create) + len(self.synonyms_to_update)
        return {
            "created": created_total,
            "updated": updated_total,
            "deactivated": len(self.to_deactivate),
            "synonym_links": synonym_links,
            "issues": len(self.issues),
        }


@dataclass
class NowTaxonomySyncResult:
    preview: SyncPreview
    import_log: Optional[TaxonomyImport]


class NowTaxonomySyncService:
    """Service that manages NOW taxonomy synchronization."""

    def __init__(self, http_get: Optional[HttpGetter] = None) -> None:
        self.http_get: HttpGetter = http_get or requests.get

    # ------------------------
    # Public API
    # ------------------------
    def preview(self) -> SyncPreview:
        accepted_records, synonym_records = self._load_remote_records()
        return self._build_preview(accepted_records, synonym_records)

    def sync(self, *, apply: bool = False) -> NowTaxonomySyncResult:
        preview = self.preview()
        if not apply:
            return NowTaxonomySyncResult(preview=preview, import_log=None)

        result_log = self._apply(preview)
        return NowTaxonomySyncResult(preview=preview, import_log=result_log)

    # ------------------------
    # Data Loading & Parsing
    # ------------------------
    def _load_remote_records(self) -> tuple[List[AcceptedRecord], List[SynonymRecord]]:
        accepted_url = self._require_setting("TAXON_NOW_ACCEPTED_URL")
        synonyms_url = self._require_setting("TAXON_NOW_SYNONYMS_URL")

        accepted_text = self._fetch_text(accepted_url)
        synonyms_text = self._fetch_text(synonyms_url)

        accepted_records = list(self._parse_accepted(io.StringIO(accepted_text)))
        synonyms_records = list(self._parse_synonyms(io.StringIO(synonyms_text), accepted_records))
        return accepted_records, synonyms_records

    def _fetch_text(self, url: str) -> str:
        response = self.http_get(url)
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    def _parse_accepted(self, stream: io.StringIO) -> Iterable[AcceptedRecord]:
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            try:
                name = _normalize_label(row.get("taxon_name", ""))
            except AttributeError:  # pragma: no cover - defensive
                logger.warning("Encountered malformed NOW accepted row: %s", row)
                continue
            if not name:
                logger.warning("Skipping NOW accepted row missing taxon name: %s", row)
                continue
            rank_value = row.get("taxon_rank") or row.get("taxon_level") or ""
            rank = _normalize_label(rank_value).lower()
            if rank in SKIPPED_RANKS:
                logger.debug("Skipping NOW accepted row with ignored rank '%s': %s", rank, row)
                continue
            author = _normalize_label(row.get("author", ""))
            source_version = _normalize_label(row.get("STG_TIME_STAMP", ""))
            external_id = build_accepted_external_id(name, rank)
            taxonomy = _extract_taxonomy(row, rank, name)
            yield AcceptedRecord(
                external_id=external_id,
                name=name,
                rank=rank,
                author_year=author,
                source_version=source_version,
                taxonomy=taxonomy,
            )

    def _parse_synonyms(
        self,
        stream: io.StringIO,
        accepted_records: Sequence[AcceptedRecord],
    ) -> Iterable[SynonymRecord]:
        accepted_by_name = {record.name.lower(): record for record in accepted_records}
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            syn_name = _normalize_label(row.get("syn_name", ""))
            accepted_name = _normalize_label(row.get("taxon_name", ""))
            if not syn_name or not accepted_name:
                logger.warning("Skipping NOW synonym row missing required names: %s", row)
                continue
            rank_value = row.get("taxon_rank") or row.get("taxon_level") or ""
            rank = _normalize_label(rank_value).lower()
            if rank in SKIPPED_RANKS:
                logger.debug("Skipping NOW synonym row with ignored rank '%s': %s", rank, row)
                continue
            author = _normalize_label(row.get("author", ""))
            source_version = _normalize_label(row.get("STG_TIME_STAMP", ""))
            accepted_record = accepted_by_name.get(accepted_name.lower())
            accepted_external_id = (
                accepted_record.external_id if accepted_record else build_accepted_external_id(accepted_name, rank)
            )
            external_id = build_synonym_external_id(syn_name, accepted_name)
            taxonomy = _extract_taxonomy(
                row,
                rank,
                syn_name,
                base=accepted_record.taxonomy if accepted_record else None,
            )
            yield SynonymRecord(
                external_id=external_id,
                name=syn_name,
                accepted_name=accepted_name,
                accepted_external_id=accepted_external_id,
                rank=rank,
                author_year=author,
                source_version=source_version,
                taxonomy=taxonomy,
            )

    # ------------------------
    # Preview & Diff
    # ------------------------
    def _build_preview(
        self,
        accepted_records: Sequence[AcceptedRecord],
        synonym_records: Sequence[SynonymRecord],
    ) -> SyncPreview:
        accepted_records = _deduplicate_records(accepted_records)
        synonym_records = _deduplicate_records(synonym_records)
        existing_taxa = list(
            Taxon.objects.filter(external_source=TaxonExternalSource.NOW).select_related("accepted_taxon")
        )
        existing_by_external_id = {taxon.external_id: taxon for taxon in existing_taxa if taxon.external_id}
        existing_by_rank_name = {
            (
                _normalize_label(taxon.taxon_name).lower(),
                (taxon.taxon_rank or "").lower(),
                taxon.status,
            ): taxon
            for taxon in existing_taxa
        }

        accepted_to_create: List[AcceptedRecord] = []
        accepted_to_update: List[AcceptedUpdate] = []
        synonyms_to_create: List[SynonymRecord] = []
        synonyms_to_update: List[SynonymUpdate] = []
        issues: List[SyncIssue] = []

        desired_ids = set()
        latest_version = _latest_version(accepted_records, synonym_records)

        for record in accepted_records:
            desired_ids.add(record.external_id)
            existing = existing_by_external_id.get(record.external_id)
            if existing is None:
                existing = existing_by_rank_name.get((record.name.lower(), record.rank, TaxonStatus.ACCEPTED))
            if existing is None:
                accepted_to_create.append(record)
                continue
            changes: Dict[str, Any] = {}
            if _normalize_label(existing.taxon_name) != record.name:
                changes["taxon_name"] = record.name
            if (existing.taxon_rank or "").lower() != record.rank:
                changes["taxon_rank"] = record.rank
            if (existing.author_year or "") != record.author_year:
                changes["author_year"] = record.author_year
            if existing.status != TaxonStatus.ACCEPTED:
                changes["status"] = TaxonStatus.ACCEPTED
            if not existing.is_active:
                changes["is_active"] = True
            if (existing.external_id or "") != record.external_id:
                changes["external_id"] = record.external_id
            if existing.source_version != record.source_version:
                changes["source_version"] = record.source_version
            for field in TAXONOMY_FIELDS:
                desired_value = record.taxonomy.get(field, TAXONOMY_DEFAULTS.get(field, ""))
                if field in TAXONOMY_DEFAULTS:
                    desired_value = desired_value or TAXONOMY_DEFAULTS[field]
                existing_value = getattr(existing, field, "")
                if _normalize_label(existing_value) != desired_value:
                    changes[field] = desired_value
            if changes:
                accepted_to_update.append(AcceptedUpdate(instance=existing, record=record, changes=changes))

        accepted_lookup = {record.external_id: record for record in accepted_records}

        for record in synonym_records:
            desired_ids.add(record.external_id)
            existing = existing_by_external_id.get(record.external_id)
            if existing is None:
                existing = existing_by_rank_name.get((record.name.lower(), record.rank, TaxonStatus.SYNONYM))
            accepted_record = accepted_lookup.get(record.accepted_external_id)
            if accepted_record is None:
                issues.append(
                    SyncIssue(
                        code="missing-accepted",
                        message="Accepted taxon referenced by synonym is missing from dataset",
                        context={"synonym": record.name, "accepted": record.accepted_name},
                    )
                )
                continue
            if existing is None:
                synonyms_to_create.append(record)
                continue
            changes = {}
            if _normalize_label(existing.taxon_name) != record.name:
                changes["taxon_name"] = record.name
            if existing.status != TaxonStatus.SYNONYM:
                changes["status"] = TaxonStatus.SYNONYM
            accepted_obj = existing.accepted_taxon
            if not accepted_obj or accepted_obj.external_id != record.accepted_external_id:
                changes["accepted_taxon"] = record.accepted_external_id
            if not existing.is_active:
                changes["is_active"] = True
            if (existing.taxon_rank or "").lower() != record.rank:
                changes["taxon_rank"] = record.rank
            if (existing.author_year or "") != record.author_year:
                changes["author_year"] = record.author_year
            if (existing.external_id or "") != record.external_id:
                changes["external_id"] = record.external_id
            if existing.source_version != record.source_version:
                changes["source_version"] = record.source_version
            for field in TAXONOMY_FIELDS:
                desired_value = record.taxonomy.get(field, TAXONOMY_DEFAULTS.get(field, ""))
                if field in TAXONOMY_DEFAULTS:
                    desired_value = desired_value or TAXONOMY_DEFAULTS[field]
                existing_value = getattr(existing, field, "")
                if _normalize_label(existing_value) != desired_value:
                    changes[field] = desired_value
            if changes:
                synonyms_to_update.append(SynonymUpdate(instance=existing, record=record, changes=changes))

        deactivate_flag = getattr(settings, "TAXON_SYNC_DEACTIVATE_MISSING", True)
        to_deactivate: List[Taxon] = []
        if deactivate_flag:
            for taxon in existing_taxa:
                if taxon.external_id and taxon.external_id not in desired_ids and taxon.is_active:
                    to_deactivate.append(taxon)

        preview = SyncPreview(
            accepted_to_create=accepted_to_create,
            accepted_to_update=accepted_to_update,
            synonyms_to_create=synonyms_to_create,
            synonyms_to_update=synonyms_to_update,
            to_deactivate=to_deactivate,
            issues=issues,
            source_version=latest_version,
        )
        return preview

    # ------------------------
    # Apply Changes
    # ------------------------
    def _apply(self, preview: SyncPreview) -> TaxonomyImport:
        deactivate_flag = getattr(settings, "TAXON_SYNC_DEACTIVATE_MISSING", True)
        with transaction.atomic():
            import_log = TaxonomyImport.objects.create(
                source=TaxonomyImport.Source.NOW,
                source_version=preview.source_version,
            )

            created_taxa: List[Taxon] = []
            if preview.accepted_to_create:
                accepted_instances = [
                    build_taxon_from_record(record, status=TaxonStatus.ACCEPTED)
                    for record in preview.accepted_to_create
                ]
                created_taxa.extend(
                    Taxon.objects.bulk_create(accepted_instances, batch_size=500, ignore_conflicts=False)
                )

            accepted_mapping = {
                taxon.external_id: taxon
                for taxon in Taxon.objects.filter(
                    external_source=TaxonExternalSource.NOW,
                    status=TaxonStatus.ACCEPTED,
                )
            }
            accepted_mapping.update({taxon.external_id: taxon for taxon in created_taxa if taxon.status == TaxonStatus.ACCEPTED})
            accepted_mapping.update(
                {update.record.external_id: update.instance for update in preview.accepted_to_update}
            )

            accepted_updates = [update for update in preview.accepted_to_update if update.changes]
            if accepted_updates:
                for item in accepted_updates:
                    apply_changes(item.instance, item.changes)
                Taxon.objects.bulk_update(
                    [item.instance for item in accepted_updates],
                    [
                        "taxon_name",
                        "taxon_rank",
                        "author_year",
                        "status",
                        "is_active",
                        "source_version",
                        "external_id",
                        "kingdom",
                        "phylum",
                        "class_name",
                        "order",
                        "superfamily",
                        "family",
                        "subfamily",
                        "tribe",
                        "genus",
                        "species",
                        "infraspecific_epithet",
                    ],
                )

            synonym_instances_to_create: List[Taxon] = []
            for record in preview.synonyms_to_create:
                accepted_taxon = accepted_mapping.get(record.accepted_external_id)
                if not accepted_taxon:
                    # Should have been captured as an issue already; skip defensively.
                    logger.warning(
                        "Skipping synonym creation because accepted taxon is missing: %s", record.accepted_external_id
                    )
                    continue
                instance = build_taxon_from_record(
                    record,
                    status=TaxonStatus.SYNONYM,
                    accepted_taxon=accepted_taxon,
                )
                synonym_instances_to_create.append(instance)
            if synonym_instances_to_create:
                created_taxa.extend(
                    Taxon.objects.bulk_create(synonym_instances_to_create, batch_size=500, ignore_conflicts=False)
                )

            synonym_updates = [update for update in preview.synonyms_to_update if update.changes]
            if synonym_updates:
                for item in synonym_updates:
                    changes = item.changes.copy()
                    accepted_external_id = changes.pop("accepted_taxon", None)
                    if accepted_external_id:
                        accepted_taxon = accepted_mapping.get(accepted_external_id) or Taxon.objects.filter(
                            external_source=TaxonExternalSource.NOW,
                            external_id=accepted_external_id,
                        ).first()
                        if not accepted_taxon:
                            logger.warning(
                                "Unable to resolve accepted taxon %s for synonym update", accepted_external_id
                            )
                            continue
                        item.instance.accepted_taxon = accepted_taxon
                    apply_changes(item.instance, changes)
                Taxon.objects.bulk_update(
                    [item.instance for item in synonym_updates],
                    [
                        "taxon_name",
                        "taxon_rank",
                        "author_year",
                        "status",
                        "accepted_taxon",
                        "is_active",
                        "source_version",
                        "external_id",
                        "kingdom",
                        "phylum",
                        "class_name",
                        "order",
                        "superfamily",
                        "family",
                        "subfamily",
                        "tribe",
                        "genus",
                        "species",
                        "infraspecific_epithet",
                    ],
                )

            deactivated_taxa: List[Taxon] = []
            if deactivate_flag and preview.to_deactivate:
                for taxon in preview.to_deactivate:
                    taxon.is_active = False
                    deactivated_taxa.append(taxon)
                Taxon.objects.bulk_update(deactivated_taxa, ["is_active"])

            counts = preview.counts
            report = {
                "accepted_created": [record.external_id for record in preview.accepted_to_create],
                "accepted_updated": [update.instance.external_id for update in preview.accepted_to_update],
                "synonyms_created": [record.external_id for record in preview.synonyms_to_create],
                "synonyms_updated": [update.instance.external_id for update in preview.synonyms_to_update],
                "deactivated": [taxon.external_id for taxon in deactivated_taxa],
                "issues": [issue.context for issue in preview.issues],
            }

            import_log.mark_finished(
                ok=len(preview.issues) == 0,
                counts=counts,
                report=report,
            )
            import_log.finished_at = timezone.now()
            import_log.save()

        return import_log

    # ------------------------
    # Helpers
    # ------------------------
    def _require_setting(self, name: str) -> str:
        value = getattr(settings, name, None)
        if not value:
            raise RuntimeError(f"Missing required NOW taxonomy setting: {name}")
        return value


def _normalize_label(value: str) -> str:
    value = value or ""
    return " ".join(value.split()).strip()


def build_accepted_external_id(name: str, rank: str) -> str:
    normalized_name = _normalize_label(name)
    normalized_rank = (_normalize_label(rank) or TaxonRankFallback.SPECIES).lower()
    return f"NOW:{normalized_rank}:{normalized_name}"


def build_synonym_external_id(synonym_name: str, accepted_name: str) -> str:
    return f"NOW:syn:{_normalize_label(synonym_name)}::accepted:{_normalize_label(accepted_name)}"


def _latest_version(
    accepted_records: Sequence[AcceptedRecord],
    synonym_records: Sequence[SynonymRecord],
) -> str:
    versions = {record.source_version for record in accepted_records if record.source_version}
    versions.update({record.source_version for record in synonym_records if record.source_version})
    if not versions:
        return ""
    return sorted(versions)[-1]


class TaxonRankFallback:
    SPECIES = "species"


def _extract_taxonomy(
    row: Dict[str, Any],
    rank: str,
    name: str,
    *,
    base: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    taxonomy: Dict[str, str] = {field: "" for field in TAXONOMY_FIELDS}
    taxonomy.update(TAXONOMY_DEFAULTS)

    if base:
        for field, value in base.items():
            if value:
                taxonomy[field] = _normalize_label(value)

    lowered_row = {(key or "").lower(): value for key, value in row.items() if key is not None}
    for field, aliases in TAXONOMY_ALIASES.items():
        for alias in aliases:
            if alias in lowered_row:
                normalized = _normalize_label(lowered_row[alias])
                if normalized:
                    taxonomy[field] = normalized
                    break

    rank_lower = (rank or "").lower()
    scope = RANK_SCOPE.get(rank_lower, [])
    for field in ["order", "superfamily", "family", "subfamily", "tribe", "genus", "species", "infraspecific_epithet"]:
        if field not in scope:
            taxonomy[field] = ""

    normalized_name = _normalize_label(name)
    genus_part, species_part, infra_part = _split_species_parts(normalized_name)

    rank_field = RANK_TO_FIELD.get(rank_lower)
    if rank_field and not taxonomy.get(rank_field):
        if rank_field == "species":
            taxonomy[rank_field] = species_part
        elif rank_field == "genus":
            taxonomy[rank_field] = genus_part or normalized_name
        elif rank_field == "infraspecific_epithet":
            taxonomy[rank_field] = infra_part
        else:
            taxonomy[rank_field] = normalized_name

    if rank_lower in {"species", "subspecies"}:
        if not taxonomy.get("genus") and genus_part:
            taxonomy["genus"] = genus_part
        if not taxonomy.get("species") and species_part:
            taxonomy["species"] = species_part
    elif rank_lower == "genus" and not taxonomy.get("genus"):
        taxonomy["genus"] = normalized_name

    if rank_lower == "subspecies" and not taxonomy.get("infraspecific_epithet"):
        taxonomy["infraspecific_epithet"] = infra_part

    for field, default in TAXONOMY_DEFAULTS.items():
        if not taxonomy.get(field):
            taxonomy[field] = default

    return taxonomy


def _split_species_parts(name: str) -> tuple[str, str, str]:
    parts = name.split()
    genus = parts[0] if parts else ""
    species = parts[1] if len(parts) > 1 else ""
    infraspecific = parts[2] if len(parts) > 2 else ""
    return genus, species, infraspecific


def _deduplicate_records(records: Sequence[AcceptedRecord | SynonymRecord]) -> List[Any]:
    unique: Dict[str, AcceptedRecord | SynonymRecord] = {}
    for record in records:
        unique[getattr(record, "external_id")] = record
    return [unique[key] for key in sorted(unique.keys())]


def build_taxon_from_record(
    record: AcceptedRecord | SynonymRecord,
    *,
    status: str,
    accepted_taxon: Optional[Taxon] = None,
) -> Taxon:
    taxon_rank_value = getattr(record, "rank", "") or TaxonRankFallback.SPECIES
    normalized_name = _normalize_label(record.name)
    taxonomy = {field: "" for field in TAXONOMY_FIELDS}
    taxonomy.update(TAXONOMY_DEFAULTS)
    taxonomy.update(getattr(record, "taxonomy", {}) or {})

    genus_part, species_part, infra_part = _split_species_parts(normalized_name)
    rank_field = RANK_TO_FIELD.get(taxon_rank_value.lower(), "")

    if rank_field and not taxonomy.get(rank_field):
        if rank_field == "species":
            taxonomy[rank_field] = species_part
        elif rank_field == "genus":
            taxonomy[rank_field] = genus_part or normalized_name
        elif rank_field == "infraspecific_epithet":
            taxonomy[rank_field] = infra_part
        else:
            taxonomy[rank_field] = normalized_name

    if taxon_rank_value.lower() in {"species", "subspecies"}:
        if not taxonomy.get("genus") and genus_part:
            taxonomy["genus"] = genus_part
        if not taxonomy.get("species") and species_part:
            taxonomy["species"] = species_part
    elif taxon_rank_value.lower() == "genus" and not taxonomy.get("genus"):
        taxonomy["genus"] = normalized_name

    if taxon_rank_value.lower() == "subspecies" and not taxonomy.get("infraspecific_epithet"):
        taxonomy["infraspecific_epithet"] = infra_part

    instance = Taxon(
        external_source=TaxonExternalSource.NOW,
        external_id=record.external_id,
        author_year=getattr(record, "author_year", ""),
        status=status,
        accepted_taxon=accepted_taxon if status == TaxonStatus.SYNONYM else None,
        is_active=True,
        source_version=getattr(record, "source_version", ""),
        taxon_rank=taxon_rank_value,
        taxon_name=normalized_name,
        kingdom=taxonomy.get("kingdom", TAXONOMY_DEFAULTS["kingdom"]),
        phylum=taxonomy.get("phylum", TAXONOMY_DEFAULTS["phylum"]),
        class_name=taxonomy.get("class_name", TAXONOMY_DEFAULTS["class_name"]),
        order=taxonomy.get("order", ""),
        superfamily=taxonomy.get("superfamily", ""),
        family=taxonomy.get("family", ""),
        subfamily=taxonomy.get("subfamily", ""),
        tribe=taxonomy.get("tribe", ""),
        genus=taxonomy.get("genus", ""),
        species=taxonomy.get("species", ""),
        infraspecific_epithet=taxonomy.get("infraspecific_epithet", ""),
    )
    return instance


def apply_changes(instance: Taxon, changes: Dict[str, Any]) -> None:
    for field, value in changes.items():
        setattr(instance, field, value)

