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
        try:
            if not isinstance(payload, dict):
                raise TypeError("GBIF payload must be a JSON object")
            usage = payload.get("usage") or {}
            diagnostics = payload.get("diagnostics") or {}
            if not isinstance(usage, dict) or not isinstance(diagnostics, dict):
                raise TypeError("GBIF usage and diagnostics must be JSON objects")
            raw_canonical = usage.get("canonicalName")
            if not isinstance(raw_canonical, str):
                raise TypeError("GBIF canonical name must be a string")
            canonical = normalize_taxon_label(raw_canonical)
            if (diagnostics.get("matchType") != "EXACT"
                    or canonical.lower() != normalize_taxon_label(name).lower()
                    or (rank and usage.get("rank", "").lower() != rank.lower())):
                raise GbifMatchError("GBIF did not return an exact name/rank match")
            classification = {}
            for item in payload.get("classification", []):
                if not isinstance(item, dict):
                    raise TypeError("GBIF classification entries must be JSON objects")
                raw_class_rank, raw_class_name = item.get("rank"), item.get("name")
                if not isinstance(raw_class_rank, str) or not isinstance(raw_class_name, str):
                    raise TypeError("GBIF classification names and ranks must be strings")
                classification[raw_class_rank.lower()] = normalize_taxon_label(raw_class_name)
            if usage.get("rank") == "CLASS":
                classification["class"] = canonical
            if not classification.get("class"):
                raise GbifMatchError("GBIF match has no taxonomic class")
            if diagnostics.get("issues"):
                raise GbifMatchError("GBIF match has diagnostic issues requiring review")
            # Preserve every decision-bearing response field in the audit version.
            version = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        except GbifMatchError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise GbifMatchError("GBIF returned a malformed match response") from exc

        def record_fields(item):
            if not isinstance(item, dict):
                raise GbifMatchError("GBIF returned a malformed taxon usage")
            raw_name = item.get("canonicalName")
            if not isinstance(raw_name, str):
                raise GbifMatchError("GBIF returned an invalid taxon name")
            item_name = normalize_taxon_label(raw_name)
            raw_rank = item.get("rank") or ""
            if not isinstance(raw_rank, str):
                raise GbifMatchError("GBIF returned an invalid taxon rank")
            item_rank = raw_rank.lower()
            if not item_name or not item.get("key") or item_rank not in TaxonRank.values:
                raise GbifMatchError("GBIF returned an unsupported rank or incomplete name")
            def optional_text(field):
                value = item.get(field)
                if value is not None and not isinstance(value, str):
                    raise GbifMatchError(f"GBIF returned an invalid {field}")
                return value or ""

            taxonomy = {field: "" for field in TAXONOMY_FIELDS}
            for field in taxonomy:
                taxonomy[field] = classification.get("class" if field == "class_name" else field, "")
            scope = RANK_SCOPE.get(item_rank, [])
            for field in ("order", "superfamily", "family", "subfamily", "tribe", "genus", "species", "infraspecific_epithet"):
                if field not in scope:
                    taxonomy[field] = ""
            if item_rank in {"genus", "species", "subspecies"} and not taxonomy["family"]:
                raise GbifMatchError("GBIF match is missing the required family")
            parts = item_name.split()
            if item_rank in {"genus", "species", "subspecies"}:
                taxonomy["genus"] = optional_text("genericName") or parts[0]
            if item_rank in {"species", "subspecies"}:
                taxonomy["species"] = optional_text("specificEpithet") or (parts[1] if len(parts) > 1 else "")
            if item_rank == "subspecies":
                taxonomy["infraspecific_epithet"] = optional_text("infraspecificEpithet") or (parts[2] if len(parts) > 2 else "")
            return dict(
                external_id=f"GBIF:{self.checklist}:{item['key']}", name=item_name, rank=item_rank,
                author_year=optional_text("authorship"), source_version=version, taxonomy=taxonomy,
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
