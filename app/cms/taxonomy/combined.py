"""Collection-scoped synchronization with NOW preference for mammals."""
from dataclasses import replace
import hashlib

import requests
from django.conf import settings

from ..models import FieldSlip, Taxon, TaxonExternalSource, TaxonomyImport
from ..utils import iter_current_identifications
from ..taxon_identity import normalize_taxon_label, taxon_identity
from .gbif import GbifClient
from .sync import NowTaxonomySyncService, SynonymRecord, SyncIssue, _latest_version, _record_rank


class TaxonomySyncService(NowTaxonomySyncService):
    def __init__(self, http_get=None, gbif_get=None):
        super().__init__(http_get=http_get)
        self.gbif = GbifClient(http_get=gbif_get)

    def preview(self):
        now_accepted, now_synonyms = self._load_remote_records()
        full_now_accepted, full_now_synonyms = now_accepted, now_synonyms
        taxa = list(Taxon.objects.all())
        names = {(normalize_taxon_label(t.taxon_name).lower(), normalize_taxon_label(t.taxon_rank).lower()) for t in taxa}
        # Free-text identifications have no known rank; retain that query even
        # when a catalogue row has the same label at a different rank. Stream the
        # values directly into the set to avoid a catalogue-sized temporary list.
        names.update(
            (name, "")
            for identification in iter_current_identifications()
            if (name := normalize_taxon_label(identification.taxon_verbatim)
                or normalize_taxon_label(identification.taxon))
        )
        names.update(
            (name, "")
            for verbatim in FieldSlip.objects.order_by().values_list("verbatim_taxon", flat=True).iterator()
            if (name := normalize_taxon_label(verbatim))
        )
        names = {(name.lower(), rank) for name, rank in names if name}
        now_accepted, now_synonyms = self._scope_records(now_accepted, now_synonyms, taxa)
        candidates = list(now_accepted) + list(now_synonyms)
        issues = []
        failed_names = set()
        blocked_now_keys = set()
        taxa_by_name = {}
        non_mammals_by_name = {}
        for taxon in taxa:
            normalized_name = normalize_taxon_label(taxon.taxon_name).lower()
            taxa_by_name.setdefault(normalized_name, []).append(taxon)
            if normalize_taxon_label(taxon.class_name).lower() not in {"", "mammalia"}:
                non_mammals_by_name.setdefault(normalized_name, []).append(taxon)
        for name, rank, result in self.gbif.match_many(names):
            try:
                if isinstance(result, Exception):
                    raise result
                accepted, synonyms = result
                candidates.extend(accepted)
                candidates.extend(synonyms)
            except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as exc:
                failed_names.add((name.lower(), _record_rank(rank) if rank else None))
                known_non_mammals = [t for t in non_mammals_by_name.get(name.lower(), [])
                                     if not rank or normalize_taxon_label(t.taxon_rank).lower() == rank]
                known_mammals = [
                    t for t in taxa_by_name.get(name.lower(), [])
                    if normalize_taxon_label(t.class_name).lower() == "mammalia"
                    and (not rank or _record_rank(t.taxon_rank) == _record_rank(rank))
                ]
                # A failed class lookup cannot safely turn a new free-text name
                # into a NOW mammal homonym. NOW is safe only for an established
                # local mammal at this identity.
                if not known_mammals:
                    blocked_now_keys.update(
                        taxon_identity(candidate.name, _record_rank(candidate.rank))
                        for candidate in candidates
                        if candidate.external_source == TaxonExternalSource.NOW
                        and candidate.name.lower() == name.lower()
                        and (not rank or _record_rank(candidate.rank) == _record_rank(rank))
                    )
                blocked_now_keys.update(taxon_identity(t.taxon_name, _record_rank(t.taxon_rank)) for t in known_non_mammals)
                if known_non_mammals or not known_mammals:
                    issues.append(SyncIssue("gbif-match", str(exc), {"name": name, "rank": rank}))

        # GBIF may resolve a local synonym to a mammal whose accepted name is
        # already in NOW, even though that accepted name was not locally entered.
        candidate_keys = {taxon_identity(r.name, _record_rank(r.rank)) for r in candidates}
        additional_synonyms = [r for r in full_now_synonyms if taxon_identity(r.name, _record_rank(r.rank)) in candidate_keys]
        dependency_ids = {r.accepted_key for r in additional_synonyms}
        candidates.extend(additional_synonyms)
        candidates.extend(r for r in full_now_accepted if taxon_identity(r.name, _record_rank(r.rank)) in candidate_keys
                          or (r.external_source, r.external_id) in dependency_ids)

        local_keys = {
            (name, _record_rank(rank)) for name, rank in names if rank
        }
        local_names_without_rank = {name for name, rank in names if not rank}
        blocked_now_dependencies = {
            record.accepted_key for record in candidates
            if isinstance(record, SynonymRecord)
            and record.external_source == TaxonExternalSource.NOW
            and taxon_identity(record.name, _record_rank(record.rank)) in blocked_now_keys
            and (record.accepted_name.lower(), _record_rank(record.rank)) not in local_keys
            and record.accepted_name.lower() not in local_names_without_rank
        }
        candidates = [r for r in candidates if not (
            r.external_source == TaxonExternalSource.NOW
            and (
                taxon_identity(r.name, _record_rank(r.rank)) in blocked_now_keys
                or (r.external_source, r.external_id) in blocked_now_dependencies
            )
        )]

        def priority(record):
            non_mammal = record.taxonomy.get("class_name", "").lower() != "mammalia"
            return (0 if record.external_source == TaxonExternalSource.GBIF and non_mammal else
                    1 if record.external_source == TaxonExternalSource.NOW else 2,
                    isinstance(record, SynonymRecord), record.external_id)

        selected = {}
        by_external = {(r.external_source, r.external_id): taxon_identity(r.name, _record_rank(r.rank)) for r in candidates}
        for record in sorted(candidates, key=priority):
            selected.setdefault(taxon_identity(record.name, _record_rank(record.rank)), record)
        accepted, synonyms = [], []
        for key, record in selected.items():
            if not isinstance(record, SynonymRecord):
                accepted.append(record)
                continue
            target = selected.get(by_external.get(record.accepted_key))
            visited = {key}
            while isinstance(target, SynonymRecord):
                target_key = taxon_identity(target.name, _record_rank(target.rank))
                if target_key in visited:
                    target = None
                    break
                visited.add(target_key)
                target = selected.get(by_external.get(target.accepted_key))
            if target is None or taxon_identity(target.name, _record_rank(target.rank)) == key:
                issues.append(SyncIssue("source-conflict", "Cannot resolve accepted taxon across sources", {"name": record.name}))
                failed_names.add((record.name.lower(), _record_rank(record.rank)))
                continue
            synonyms.append(replace(record, accepted_external_id=target.external_id, accepted_external_source=target.external_source,
                                    accepted_name=target.name))
        preview = self._build_preview(accepted, synonyms)
        # A missing or failed lookup is not evidence that an existing taxon disappeared.
        preview.to_deactivate = [
            taxon for taxon in preview.to_deactivate
            if (normalize_taxon_label(taxon.taxon_name).lower(), _record_rank(taxon.taxon_rank)) not in failed_names
            and (normalize_taxon_label(taxon.taxon_name).lower(), None) not in failed_names
        ]
        preview.issues.extend(issues)
        preview.import_source = TaxonomyImport.Source.COMBINED
        gbif_hashes = sorted({record.source_version for record in candidates
                              if record.external_source == TaxonExternalSource.GBIF and record.source_version})
        gbif_version = hashlib.sha256(";".join(gbif_hashes).encode()).hexdigest() if gbif_hashes else "none"
        preview.source_version = f"NOW:{_latest_version(full_now_accepted, full_now_synonyms)}; GBIF:{settings.TAXON_GBIF_CHECKLIST_KEY}:{gbif_version}"
        return preview
