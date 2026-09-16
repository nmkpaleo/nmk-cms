"""GBIF v2 matching against the configured Catalogue of Life checklist."""
from concurrent.futures import ThreadPoolExecutor
from itertools import islice

import hashlib
import json
from urllib.parse import urlencode

import requests
from django.conf import settings

from ..models import TaxonExternalSource, TaxonRank
from ..taxon_identity import normalize_taxon_label
from .sync import AcceptedRecord, SynonymRecord, TAXONOMY_FIELDS, RANK_SCOPE


class GbifMatchError(ValueError):
    pass


class GbifClient:
    def __init__(self, http_get=None):
        self.http_get = http_get or requests.get
        self.checklist = settings.TAXON_GBIF_CHECKLIST_KEY
        self.results = {}

    def match_many(self, names):
        """Bound in-flight requests and stop contacting an unavailable service."""
        workers = max(1, min(16, settings.TAXON_GBIF_WORKERS))
        pending = iter(sorted(set(names)))

        def lookup(item):
            try:
                return self.match(*item)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                return exc

        with ThreadPoolExecutor(max_workers=workers) as executor:
            while batch := list(islice(pending, workers)):
                results = list(executor.map(lookup, batch))
                for (name, rank), result in zip(batch, results):
                    yield name, rank, result
                # Exact-name misses do not open the circuit. A whole batch of
                # transport/HTTP failures does, avoiding one timeout per taxon.
                if all(isinstance(result, requests.RequestException) for result in results):
                    for name, rank in pending:
                        yield name, rank, requests.RequestException(
                            "GBIF lookups deferred after service failures; retry the preview later"
                        )
                    break

    def match(self, name, rank=""):
        key = (name.lower(), rank.lower())
        if key not in self.results:
            params = {"scientificName": name, "checklistKey": self.checklist}
            if rank:
                params["taxonRank"] = rank.upper()
            response = self.http_get(
                settings.TAXON_GBIF_MATCH_URL + "?" + urlencode(params),
                timeout=settings.TAXON_GBIF_TIMEOUT,
            )
            response.raise_for_status()
            self.results[key] = self.parse(response.json(), name, rank)
        return self.results[key]

    def parse(self, payload, name, rank=""):
        usage = payload.get("usage") or {}
        diagnostics = payload.get("diagnostics") or {}
        canonical = normalize_taxon_label(usage.get("canonicalName"))
        if (diagnostics.get("matchType") != "EXACT"
                or canonical.lower() != normalize_taxon_label(name).lower()
                or (rank and usage.get("rank", "").lower() != rank.lower())):
            raise GbifMatchError("GBIF did not return an exact name/rank match")
        classification = {item["rank"].lower(): item["name"] for item in payload.get("classification", [])}
        if usage.get("rank") == "CLASS":
            classification["class"] = canonical
        if not classification.get("class"):
            raise GbifMatchError("GBIF match has no taxonomic class")
        if diagnostics.get("issues"):
            raise GbifMatchError("GBIF match has diagnostic issues requiring review")
        version = hashlib.sha256(json.dumps(
            {"usage": usage, "accepted": payload.get("acceptedUsage"), "classification": classification},
            sort_keys=True,
        ).encode()).hexdigest()

        def record_fields(item):
            item_name = normalize_taxon_label(item.get("canonicalName"))
            item_rank = item.get("rank", "").lower()
            if not item_name or not item.get("key") or item_rank not in TaxonRank.values:
                raise GbifMatchError("GBIF returned an unsupported rank or incomplete name")
            taxonomy = {field: "" for field in TAXONOMY_FIELDS}
            for field in taxonomy:
                taxonomy[field] = classification.get("class" if field == "class_name" else field, "")
            scope = RANK_SCOPE.get(item_rank, [])
            for field in ("order", "superfamily", "family", "subfamily", "tribe", "genus", "species", "infraspecific_epithet"):
                if field not in scope:
                    taxonomy[field] = ""
            parts = item_name.split()
            if item_rank in {"genus", "species", "subspecies"}:
                taxonomy["genus"] = item.get("genericName") or parts[0]
            if item_rank in {"species", "subspecies"}:
                taxonomy["species"] = item.get("specificEpithet") or (parts[1] if len(parts) > 1 else "")
            if item_rank == "subspecies":
                taxonomy["infraspecific_epithet"] = item.get("infraspecificEpithet") or (parts[2] if len(parts) > 2 else "")
            return dict(
                external_id=f"GBIF:{self.checklist}:{item['key']}", name=item_name, rank=item_rank,
                author_year=item.get("authorship", ""), source_version=version, taxonomy=taxonomy,
                external_source=TaxonExternalSource.GBIF,
            )

        if payload.get("synonym"):
            target = payload.get("acceptedUsage") or {}
            accepted = AcceptedRecord(**record_fields(target))
            synonym = SynonymRecord(**record_fields(usage), accepted_name=accepted.name,
                                    accepted_external_id=accepted.external_id)
            return [accepted], [synonym]
        if usage.get("status") != "ACCEPTED":
            raise GbifMatchError("GBIF usage is not accepted")
        return [AcceptedRecord(**record_fields(usage))], []
