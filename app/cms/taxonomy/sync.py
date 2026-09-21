"""NOW taxonomy synchronization service layer."""
from __future__ import annotations

import csv
import hashlib
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import requests
from django.conf import settings
from django.db import transaction, DataError, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..taxon_identity import taxon_identity
from ..models import (
    FieldSlip,
    Identification,
    Taxon,
    TaxonExternalSource,
    TaxonStatus,
    TaxonomyImport,
)
from ..utils import iter_current_identifications

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
    external_source: str = TaxonExternalSource.NOW


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
    external_source: str = TaxonExternalSource.NOW
    accepted_external_source: str = ""

    @property
    def accepted_key(self):
        return (self.accepted_external_source or self.external_source, self.accepted_external_id)


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
    previous: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SynonymUpdate:
    instance: Taxon
    record: SynonymRecord
    changes: Dict[str, Any]
    previous: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncPreview:
    accepted_to_create: List[AcceptedRecord]
    accepted_to_update: List[AcceptedUpdate]
    synonyms_to_create: List[SynonymRecord]
    synonyms_to_update: List[SynonymUpdate]
    to_deactivate: List[Taxon]
    issues: List[SyncIssue]
    source_version: str
    import_source: str = TaxonomyImport.Source.NOW
    identifications_linked: int = 0

    @property
    def counts(self) -> Dict[str, Any]:
        created_total = len(self.accepted_to_create) + len(self.synonyms_to_create)
        updated_total = len(self.accepted_to_update) + len(self.synonyms_to_update)
        synonym_links = len(self.synonyms_to_create) + len(self.synonyms_to_update)
        counts = {
            "created": created_total,
            "updated": updated_total,
            "deactivated": len(self.to_deactivate),
            "synonym_links": synonym_links,
            "issues": len(self.issues),
        }
        if self.identifications_linked:
            counts["identifications_linked"] = self.identifications_linked
        return counts


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
        accepted_by_identity = {
            (record.name.lower(), _record_rank(record.rank)): record
            for record in accepted_records
        }
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
            accepted_record = accepted_by_identity.get((accepted_name.lower(), _record_rank(rank)))
            accepted_external_id = (
                accepted_record.external_id if accepted_record else build_accepted_external_id(accepted_name, rank)
            )
            external_id = build_synonym_external_id(syn_name, accepted_name, rank)
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
    def _scope_records(
        self,
        accepted_records: Sequence[AcceptedRecord],
        synonym_records: Sequence[SynonymRecord],
        existing_taxa: Sequence[Taxon],
        local_names: set[str] | None = None,
    ) -> tuple[List[AcceptedRecord], List[SynonymRecord]]:
        """Keep local names and accepted targets needed by their synonyms."""
        taxon_keys = {
            taxon_identity(taxon.taxon_name, _record_rank(taxon.taxon_rank))
            for taxon in existing_taxa
        }
        # DrawerRegister.taxa and Identification.taxon_record already point to
        # existing_taxa. Free text is unranked and therefore matches by name.
        if local_names is None:
            names = {
                (_normalize_label(identification.taxon_verbatim)
                 or _normalize_label(identification.taxon)).lower()
                for identification in iter_current_identifications()
            }
            names.update(
                _normalize_label(name).lower()
                for name in FieldSlip.objects.order_by().values_list("verbatim_taxon", flat=True).iterator()
            )
        else:
            names = set(local_names)
        names.discard("")
        existing_ids = {
            taxon.external_id for taxon in existing_taxa
            if taxon.external_source == TaxonExternalSource.NOW and taxon.external_id
        }
        synonyms = [
            record for record in synonym_records
            if taxon_identity(record.name, _record_rank(record.rank)) in taxon_keys
            or record.name.lower() in names
            or (record.external_source == TaxonExternalSource.NOW and record.external_id in existing_ids)
        ]
        accepted_ids = {record.accepted_key for record in synonyms}
        accepted = [
            record for record in accepted_records
            if taxon_identity(record.name, _record_rank(record.rank)) in taxon_keys
            or record.name.lower() in names
            or (record.external_source == TaxonExternalSource.NOW and record.external_id in existing_ids)
            or (record.external_source, record.external_id) in accepted_ids
        ]
        # Once an accepted taxon is in scope, retain all of its NOW synonyms.
        # This lets historical identifications resolve without importing taxa
        # unrelated to the collection.
        accepted_keys = {(record.external_source, record.external_id) for record in accepted}
        synonyms = [
            record for record in synonym_records
            if taxon_identity(record.name, _record_rank(record.rank)) in taxon_keys
            or record.name.lower() in names
            or (record.external_source == TaxonExternalSource.NOW and record.external_id in existing_ids)
            or record.accepted_key in accepted_keys
        ]
        return accepted, synonyms

    def _build_preview(
        self,
        accepted_records: Sequence[AcceptedRecord],
        synonym_records: Sequence[SynonymRecord],
        local_names: set[str] | None = None,
    ) -> SyncPreview:
        accepted_records = _deduplicate_records(accepted_records)
        synonym_records = _deduplicate_records(synonym_records)
        latest_version = _latest_version(accepted_records, synonym_records)
        all_taxa = list(Taxon.objects.select_related("accepted_taxon"))
        accepted_records, synonym_records = self._scope_records(
            accepted_records, synonym_records, all_taxa, local_names=local_names
        )
        existing_taxa = all_taxa
        existing_by_external_id = {(taxon.external_source, taxon.external_id): taxon for taxon in existing_taxa if taxon.external_id}
        existing_by_rank_name = {taxon_identity(t.taxon_name, t.taxon_rank): t for t in existing_taxa}
        desired_keys = {taxon_identity(r.name, _record_rank(r.rank)) for r in accepted_records + synonym_records}
        source_conflicts = {}

        def find_existing(record):
            key = taxon_identity(record.name, _record_rank(record.rank))
            existing = existing_by_rank_name.get(key)
            candidate = existing_by_external_id.get((record.external_source, record.external_id))
            if candidate and existing and candidate.pk != existing.pk:
                source_conflicts[(record.external_source, record.external_id)] = (existing, candidate)
                return None
            if existing is None and candidate:
                # A usage key can move to a newly accepted name while the old
                # name remains as a synonym. Keep that synonym's row separate.
                if taxon_identity(candidate.taxon_name, candidate.taxon_rank) not in desired_keys:
                    existing = candidate
            return existing

        def has_source_conflict(record):
            conflict = source_conflicts.get((record.external_source, record.external_id))
            if conflict is None:
                return False
            matched_taxon_ids.update(taxon.pk for taxon in conflict)
            issues.append(SyncIssue(
                "source-id-conflict",
                "Source ID belongs to a different local taxon with the same incoming identity",
                {"name": record.name, "external_id": record.external_id},
            ))
            return True


        accepted_to_create: List[AcceptedRecord] = []
        accepted_to_update: List[AcceptedUpdate] = []
        synonyms_to_create: List[SynonymRecord] = []
        synonyms_to_update: List[SynonymUpdate] = []
        issues: List[SyncIssue] = []

        desired_ids = set()
        matched_taxon_ids = set()

        for record in accepted_records:
            desired_ids.add((record.external_source, record.external_id))
            existing = find_existing(record)
            if has_source_conflict(record):
                continue
            if existing is None:
                accepted_to_create.append(record)
                continue
            matched_taxon_ids.add(existing.pk)
            changes: Dict[str, Any] = {}
            if existing.external_source != record.external_source:
                changes["external_source"] = record.external_source
            if existing.accepted_taxon_id:
                changes["accepted_taxon"] = None
            if _normalize_label(existing.taxon_name) != record.name:
                changes["taxon_name"] = record.name
            if (existing.taxon_rank or "").lower() != _record_rank(record.rank):
                changes["taxon_rank"] = _record_rank(record.rank)
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
                if record.external_source == TaxonExternalSource.NOW and field in TAXONOMY_DEFAULTS:
                    desired_value = desired_value or TAXONOMY_DEFAULTS[field]
                existing_value = getattr(existing, field, "")
                if _normalize_label(existing_value) != desired_value:
                    changes[field] = desired_value
            if changes:
                accepted_to_update.append(AcceptedUpdate(instance=existing, record=record, changes=changes))

        accepted_lookup = {(record.external_source, record.external_id): record for record in accepted_records}

        for record in synonym_records:
            desired_ids.add((record.external_source, record.external_id))
            existing = find_existing(record)
            if has_source_conflict(record):
                continue
            if existing is not None:
                # Presence upstream is enough to retain this local synonym when
                # its accepted target is temporarily absent from the export.
                matched_taxon_ids.add(existing.pk)
            accepted_record = accepted_lookup.get(record.accepted_key)
            if accepted_record is None:
                accepted_instance = (
                    existing_by_external_id.get(record.accepted_key)
                    or existing_by_rank_name.get(taxon_identity(record.accepted_name, _record_rank(record.rank)))
                )
                if accepted_instance is not None:
                    matched_taxon_ids.add(accepted_instance.pk)
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
            matched_taxon_ids.add(existing.pk)
            if existing.status == TaxonStatus.ACCEPTED and Taxon.objects.filter(accepted_taxon=existing).exists():
                issues.append(SyncIssue("unsafe-demotion", "Cannot demote an accepted taxon with unscoped dependent synonyms", {"name": existing.taxon_name}))
                continue
            changes = {}
            if existing.external_source != record.external_source:
                changes["external_source"] = record.external_source
            if _normalize_label(existing.taxon_name) != record.name:
                changes["taxon_name"] = record.name
            if existing.status != TaxonStatus.SYNONYM:
                changes["status"] = TaxonStatus.SYNONYM
            accepted_obj = existing.accepted_taxon
            if not accepted_obj or (accepted_obj.external_source, accepted_obj.external_id) != record.accepted_key:
                changes["accepted_taxon"] = record.accepted_external_id
            if not existing.is_active:
                changes["is_active"] = True
            if (existing.taxon_rank or "").lower() != _record_rank(record.rank):
                changes["taxon_rank"] = _record_rank(record.rank)
            if (existing.author_year or "") != record.author_year:
                changes["author_year"] = record.author_year
            if (existing.external_id or "") != record.external_id:
                changes["external_id"] = record.external_id
            if existing.source_version != record.source_version:
                changes["source_version"] = record.source_version
            for field in TAXONOMY_FIELDS:
                desired_value = record.taxonomy.get(field, TAXONOMY_DEFAULTS.get(field, ""))
                if record.external_source == TaxonExternalSource.NOW and field in TAXONOMY_DEFAULTS:
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
                # Fallback matches can replace an external ID (for example when
                # a synonym's accepted name changes). Preserve the matched row.
                if (
                    taxon.external_source == TaxonExternalSource.NOW
                    and taxon.pk not in matched_taxon_ids
                    and taxon.external_id
                    and (taxon.external_source, taxon.external_id) not in desired_ids
                    and taxon.is_active
                ):
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
        """Save independent groups even when another group contains invalid data."""
        categories = ("accepted_to_create", "accepted_to_update", "synonyms_to_create",
                      "synonyms_to_update", "to_deactivate")
        successful = {name: [] for name in categories}
        with transaction.atomic():
            import_log = TaxonomyImport.objects.create(
                source=preview.import_source, source_version=preview.source_version,
            )
            def apply_group(group):
                try:
                    with transaction.atomic():
                        self._apply_changes(group)
                except (DataError, IntegrityError, ValidationError) as exc:
                    names = [r.name for r in group.accepted_to_create + group.synonyms_to_create]
                    names += [u.record.name for u in group.accepted_to_update + group.synonyms_to_update]
                    names += [t.taxon_name for t in group.to_deactivate]
                    logger.exception("Skipping taxonomy sync group: %s", names)
                    preview.issues.append(SyncIssue("apply-failed", str(exc), {"taxa": names}))
                    return False
                for category in categories:
                    successful[category].extend(getattr(group, category))
                return True

            groups = list(self._apply_groups(preview))
            # Fast-path independent groups in bulk. If a batch has a data error,
            # retry its dependency groups individually so only the bad group is skipped.
            for start in range(0, len(groups), 500):
                batch = groups[start:start + 500]
                if len(batch) == 1:
                    apply_group(batch[0])
                    continue
                merged = SyncPreview(
                    **{category: [item for group in batch for item in getattr(group, category)]
                       for category in categories},
                    issues=[], source_version=preview.source_version, import_source=preview.import_source,
                )
                try:
                    with transaction.atomic():
                        self._apply_changes(merged)
                except (DataError, IntegrityError, ValidationError):
                    for group in batch:
                        apply_group(group)
                else:
                    for group in batch:
                        for category in categories:
                            successful[category].extend(getattr(group, category))
            for category in categories:
                setattr(preview, category, successful[category])
            try:
                with transaction.atomic():
                    preview.identifications_linked = self._link_identifications()
            except (DataError, IntegrityError, ValidationError) as exc:
                logger.exception("Taxonomy saved but identification linkage failed")
                preview.issues.append(SyncIssue("identification-link", str(exc)))
            source_id = lambda record: f"{record.external_source}:{record.external_id}"
            report = {
                "accepted_created": [source_id(r) for r in preview.accepted_to_create],
                "accepted_updated": [source_id(u.record) for u in preview.accepted_to_update],
                "synonyms_created": [source_id(r) for r in preview.synonyms_to_create],
                "synonyms_updated": [source_id(u.record) for u in preview.synonyms_to_update],
                "deactivated": [source_id(t) for t in preview.to_deactivate],
                "identifications_linked": preview.identifications_linked,
                "issues": [{"code": i.code, "message": i.message, **i.context} for i in preview.issues],
                "sources": sorted({r.external_source for r in preview.accepted_to_create + preview.synonyms_to_create}
                                  | {u.record.external_source for u in preview.accepted_to_update + preview.synonyms_to_update}),
            }
            import_log.mark_finished(ok=not preview.issues, counts=preview.counts, report=report)
        return import_log

    def _apply_groups(self, preview):
        """Keep synonyms, their accepted taxa, and source-ID transfers atomic."""
        categories = ("accepted_to_create", "accepted_to_update", "synonyms_to_create",
                      "synonyms_to_update", "to_deactivate")
        operations = [(category, item) for category in categories for item in getattr(preview, category)]
        parents = list(range(len(operations)))
        owners = {}

        def root(index):
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        for index, (category, item) in enumerate(operations):
            record = getattr(item, "record", item)
            instance = getattr(item, "instance", item if category == "to_deactivate" else None)
            keys = [("external", record.external_source, record.external_id)]
            if category != "to_deactivate":
                keys.append(("identity", taxon_identity(record.name, _record_rank(record.rank))))
            if isinstance(record, SynonymRecord):
                keys.append(("external", *record.accepted_key))
            if instance is not None:
                keys.extend([("pk", instance.pk), ("external", instance.external_source, instance.external_id)])
                if instance.accepted_taxon_id:
                    keys.append(("pk", instance.accepted_taxon_id))
            for key in keys:
                if key[-1] is None or key[-1] == "":
                    continue
                if key in owners:
                    parents[root(index)] = root(owners[key])
                owners[key] = index
        groups = {}
        for index, (category, item) in enumerate(operations):
            group = groups.setdefault(root(index), {name: [] for name in categories})
            group[category].append(item)
        for data in groups.values():
            yield SyncPreview(**data, issues=[], source_version=preview.source_version,
                              import_source=preview.import_source)

    def _apply_changes(self, preview):
        deactivate_flag = getattr(settings, "TAXON_SYNC_DEACTIVATE_MISSING", True)
        for record in (preview.accepted_to_create + preview.synonyms_to_create
                       + [u.record for u in preview.accepted_to_update + preview.synonyms_to_update]):
            values = {"taxon_name": record.name, "taxon_rank": record.rank,
                      "author_year": record.author_year, "source_version": record.source_version,
                      "external_id": record.external_id, **record.taxonomy}
            for name, value in values.items():
                limit = Taxon._meta.get_field(name).max_length
                if limit and value and len(value) > limit:
                    raise ValidationError(f"{record.name}: {name} exceeds {limit} characters")
        # Release changing source IDs before creates: a former accepted
        # usage can keep its row as a synonym while its old ID moves to the
        # new accepted name. This is atomic with the remaining changes.
        changing_ids = [u.instance.pk for u in preview.accepted_to_update + preview.synonyms_to_update
                        if "external_id" in u.changes]
        Taxon.objects.filter(pk__in=changing_ids).update(external_id=None)
        if preview.accepted_to_create:
            accepted_instances = [
                build_taxon_from_record(record, status=TaxonStatus.ACCEPTED)
                for record in preview.accepted_to_create
            ]
            Taxon.objects.bulk_create(accepted_instances, batch_size=500, ignore_conflicts=False)

        accepted_updates = [update for update in preview.accepted_to_update if update.changes]
        if accepted_updates:
            for item in accepted_updates:
                item.previous = item.previous or {field: getattr(item.instance, field) for field in item.changes}
                apply_changes(item.instance, item.changes)
            Taxon.objects.bulk_update(
                [item.instance for item in accepted_updates],
                [
                    "identity_key",
                    "external_source",
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

        # Reload after both inserts and updates. Some backends (including MySQL)
        # do not populate primary keys on objects passed to bulk_create.
        needed_targets = {r.accepted_key for r in preview.synonyms_to_create}
        needed_targets.update(u.record.accepted_key for u in preview.synonyms_to_update)
        accepted_mapping = {
            (taxon.external_source, taxon.external_id): taxon
            for taxon in Taxon.objects.filter(
                status=TaxonStatus.ACCEPTED, external_id__in={key[1] for key in needed_targets},
            )
        }

        synonym_instances_to_create: List[Taxon] = []
        for record in preview.synonyms_to_create:
            accepted_taxon = accepted_mapping.get(record.accepted_key)
            if not accepted_taxon:
                # Should have been captured as an issue already; skip defensively.
                logger.warning(
                    "Skipping synonym creation because accepted taxon is missing: %s", record.accepted_external_id
                )
                raise ValidationError("Accepted taxon could not be resolved")
            instance = build_taxon_from_record(
                record,
                status=TaxonStatus.SYNONYM,
                accepted_taxon=accepted_taxon,
            )
            synonym_instances_to_create.append(instance)
        if synonym_instances_to_create:
            Taxon.objects.bulk_create(synonym_instances_to_create, batch_size=500, ignore_conflicts=False)

        synonym_updates = [update for update in preview.synonyms_to_update if update.changes]
        if synonym_updates:
            for item in synonym_updates:
                item.previous = item.previous or {field: getattr(item.instance, field) for field in item.changes}
                changes = item.changes.copy()
                accepted_external_id = changes.pop("accepted_taxon", None)
                if accepted_external_id:
                    accepted_taxon = accepted_mapping.get(item.record.accepted_key)
                    if not accepted_taxon:
                        logger.warning(
                            "Unable to resolve accepted taxon %s for synonym update", accepted_external_id
                        )
                        raise ValidationError("Accepted taxon could not be resolved")
                    item.instance.accepted_taxon = accepted_taxon
                apply_changes(item.instance, changes)
            Taxon.objects.bulk_update(
                [item.instance for item in synonym_updates],
                [
                    "identity_key",
                    "external_source",
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


    def _link_identifications(self):
        """Link previously ambiguous or unlinked names without changing recorded text."""
        by_name = {}
        for taxon in Taxon.objects.filter(is_active=True).select_related("accepted_taxon"):
            target = taxon if taxon.status == TaxonStatus.ACCEPTED else taxon.accepted_taxon
            if target and target.is_active and target.status == TaxonStatus.ACCEPTED:
                by_name.setdefault(_normalize_label(taxon.taxon_name).lower(), set()).add(target.pk)
        changed = []
        for identification in Identification.objects.all().iterator():
            name = (_normalize_label(identification.taxon_verbatim)
                    or _normalize_label(identification.taxon)).lower()
            targets = by_name.get(name, set())
            if len(targets) == 1:
                target_id = next(iter(targets))
                if identification.taxon_record_id != target_id:
                    identification.taxon_record_id = target_id
                    changed.append(identification)
        if changed:
            from simple_history.utils import bulk_update_with_history
            bulk_update_with_history(changed, Identification, ["taxon_record"],
                                     default_change_reason="Linked during taxonomy sync")
        return len(changed)

    # ------------------------
    # Helpers
    # ------------------------
    def _require_setting(self, name: str) -> str:
        value = getattr(settings, name, None)
        if not value:
            raise RuntimeError(f"Missing required NOW taxonomy setting: {name}")
        return value


def _record_rank(value: str) -> str:
    return (_normalize_label(value) or TaxonRankFallback.SPECIES).lower()


def _normalize_label(value: str) -> str:
    value = value or ""
    return " ".join(value.split()).strip()


def _bounded_now_id(value: str) -> str:
    # Preserve existing IDs; hash the complete value only when it cannot fit.
    if len(value) <= 191:
        return value
    return "NOW:sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_accepted_external_id(name: str, rank: str) -> str:
    normalized_name = _normalize_label(name)
    normalized_rank = (_normalize_label(rank) or TaxonRankFallback.SPECIES).lower()
    return _bounded_now_id(f"NOW:{normalized_rank}:{normalized_name}")


def build_synonym_external_id(synonym_name: str, accepted_name: str, rank: str = "") -> str:
    return _bounded_now_id(
        f"NOW:syn:{_record_rank(rank)}:{_normalize_label(synonym_name)}::accepted:{_normalize_label(accepted_name)}"
    )


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
    unique: Dict[tuple[str, str], AcceptedRecord | SynonymRecord] = {}
    for record in records:
        unique[(record.external_source, record.external_id)] = record
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
        identity_key=taxon_identity(normalized_name, taxon_rank_value),
        external_source=record.external_source,
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
    instance.identity_key = taxon_identity(instance.taxon_name, instance.taxon_rank)

