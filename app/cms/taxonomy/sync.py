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


@dataclass(frozen=True)
class AcceptedRecord:
    """Parsed representation of an accepted NOW taxon."""

    external_id: str
    name: str
    rank: str
    author_year: str
    source_version: str


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
            rank = _normalize_label(row.get("taxon_level", "")).lower()
            author = _normalize_label(row.get("author", ""))
            source_version = _normalize_label(row.get("STG_TIME_STAMP", ""))
            external_id = build_accepted_external_id(name, rank)
            yield AcceptedRecord(
                external_id=external_id,
                name=name,
                rank=rank,
                author_year=author,
                source_version=source_version,
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
            rank = _normalize_label(row.get("taxon_level", "")).lower()
            author = _normalize_label(row.get("author", ""))
            source_version = _normalize_label(row.get("STG_TIME_STAMP", ""))
            accepted_record = accepted_by_name.get(accepted_name.lower())
            accepted_external_id = (
                accepted_record.external_id if accepted_record else build_accepted_external_id(accepted_name, rank)
            )
            external_id = build_synonym_external_id(syn_name, accepted_name)
            yield SynonymRecord(
                external_id=external_id,
                name=syn_name,
                accepted_name=accepted_name,
                accepted_external_id=accepted_external_id,
                rank=rank,
                author_year=author,
                source_version=source_version,
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
                accepted_to_create.append(record)
                continue
            changes: Dict[str, Any] = {}
            if _normalize_label(existing.name) != record.name:
                changes["name"] = record.name
            if (existing.rank or "").lower() != record.rank:
                changes["rank"] = record.rank
            if (existing.author_year or "") != record.author_year:
                changes["author_year"] = record.author_year
            if existing.status != TaxonStatus.ACCEPTED:
                changes["status"] = TaxonStatus.ACCEPTED
            if not existing.is_active:
                changes["is_active"] = True
            if existing.source_version != record.source_version:
                changes["source_version"] = record.source_version
            if changes:
                accepted_to_update.append(AcceptedUpdate(instance=existing, record=record, changes=changes))

        accepted_lookup = {record.external_id: record for record in accepted_records}

        for record in synonym_records:
            desired_ids.add(record.external_id)
            existing = existing_by_external_id.get(record.external_id)
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
            if _normalize_label(existing.name) != record.name:
                changes["name"] = record.name
            if existing.status != TaxonStatus.SYNONYM:
                changes["status"] = TaxonStatus.SYNONYM
            accepted_obj = existing.accepted_taxon
            if not accepted_obj or accepted_obj.external_id != record.accepted_external_id:
                changes["accepted_taxon"] = record.accepted_external_id
            if not existing.is_active:
                changes["is_active"] = True
            if (existing.rank or "").lower() != record.rank:
                changes["rank"] = record.rank
            if (existing.author_year or "") != record.author_year:
                changes["author_year"] = record.author_year
            if existing.source_version != record.source_version:
                changes["source_version"] = record.source_version
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
            accepted_mapping.update({update.instance.external_id: update.instance for update in preview.accepted_to_update})

            accepted_updates = [update for update in preview.accepted_to_update if update.changes]
            if accepted_updates:
                for item in accepted_updates:
                    apply_changes(item.instance, item.changes)
                Taxon.objects.bulk_update(
                    [item.instance for item in accepted_updates],
                    [
                        "name",
                        "rank",
                        "author_year",
                        "status",
                        "is_active",
                        "source_version",
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
                        "name",
                        "rank",
                        "author_year",
                        "status",
                        "accepted_taxon",
                        "is_active",
                        "source_version",
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
    # Legacy fields defaulted with generic placeholders to satisfy existing schema requirements.
    name_parts = record.name.split()
    genus = name_parts[0] if name_parts else "Unknown"
    species = name_parts[1] if len(name_parts) > 1 else genus

    taxon_rank_value = getattr(record, "rank", "") or TaxonRankFallback.SPECIES
    instance = Taxon(
        external_source=TaxonExternalSource.NOW,
        external_id=record.external_id,
        name=record.name,
        rank=getattr(record, "rank", ""),
        author_year=getattr(record, "author_year", ""),
        status=status,
        accepted_taxon=accepted_taxon if status == TaxonStatus.SYNONYM else None,
        is_active=True,
        source_version=getattr(record, "source_version", ""),
        taxon_rank=taxon_rank_value,
        taxon_name=record.name,
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Unknown",
        family="Unknown",
        genus=genus,
        species=species,
    )
    return instance


def apply_changes(instance: Taxon, changes: Dict[str, Any]) -> None:
    for field, value in changes.items():
        setattr(instance, field, value)

