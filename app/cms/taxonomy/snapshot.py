"""Signed, user-bound preview snapshots; apply never refetches remote sources."""
import hashlib
import json
from dataclasses import asdict
from uuid import uuid4

from django.core.cache import cache
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from ..models import Taxon, Identification, FieldSlip
from .sync import (AcceptedRecord, AcceptedUpdate, SynonymRecord, SynonymUpdate,
                   SyncIssue, SyncPreview, NowTaxonomySyncResult)

SALT = "cms.taxonomy.preview.v2"
MAX_AGE = 3600


class PreviewUnavailable(ValueError):
    pass


def _preview_cache_key():
    return f"taxonomy-sync-preview:{uuid4().hex}"


def _serialize_preview(preview):
    data = {
        "source_version": preview.source_version,
        "import_source": getattr(preview, "import_source", "NOW_GBIF"),
        "accepted_to_create": [asdict(r) for r in preview.accepted_to_create],
        "synonyms_to_create": [asdict(r) for r in preview.synonyms_to_create],
        "to_deactivate": [t.pk for t in preview.to_deactivate],
        "issues": [asdict(i) for i in preview.issues],
    }
    for category in ("accepted_to_update", "synonyms_to_update"):
        data[category] = [{"pk": u.instance.pk, "record": asdict(u.record), "changes": u.changes}
                          for u in getattr(preview, category)]
    return data


def _deserialize_preview(data, taxa):
    return SyncPreview(
        accepted_to_create=[AcceptedRecord(**r) for r in data["accepted_to_create"]],
        synonyms_to_create=[SynonymRecord(**r) for r in data["synonyms_to_create"]],
        accepted_to_update=[AcceptedUpdate(taxa[u["pk"]], AcceptedRecord(**u["record"]), u["changes"])
                            for u in data["accepted_to_update"]],
        synonyms_to_update=[SynonymUpdate(taxa[u["pk"]], SynonymRecord(**u["record"]), u["changes"])
                            for u in data["synonyms_to_update"]],
        to_deactivate=[taxa[pk] for pk in data["to_deactivate"]],
        issues=[SyncIssue(**i) for i in data["issues"]],
        source_version=data["source_version"],
        import_source=data.get("import_source", "NOW_GBIF"),
    )


def catalogue_fingerprint():
    """Hash relevant rows incrementally to avoid materializing the catalogue."""
    digest = hashlib.sha256()
    for label, rows in (
        ("taxa", Taxon.objects.order_by("pk").values().iterator(chunk_size=1000)),
        ("identifications", Identification.objects.order_by("pk").values_list(
            "pk", "taxon_verbatim", "taxon", "taxon_record_id").iterator(chunk_size=1000)),
        ("field_slips", FieldSlip.objects.order_by("pk").values_list(
            "pk", "verbatim_taxon").iterator(chunk_size=1000)),
    ):
        digest.update(label.encode())
        for row in rows:
            digest.update(json.dumps(row, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":")).encode())
            digest.update(b"\n")
    return digest.hexdigest()


def sign_preview(preview, user_id, fingerprint):
    preview_key = _preview_cache_key()
    cache.set(preview_key, _serialize_preview(preview), timeout=MAX_AGE)
    data = {"user": user_id, "fingerprint": fingerprint, "preview_key": preview_key}
    return signing.dumps(data, salt=SALT)


def apply_signed_preview(token, user_id, service):
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.SignatureExpired as exc:
        raise PreviewUnavailable("This preview is missing, expired, or invalid. Generate a new preview.") from exc
    except signing.BadSignature as exc:
        raise PreviewUnavailable("This preview is missing, expired, or invalid. Generate a new preview.") from exc
    if data.get("user") != user_id:
        raise PreviewUnavailable("This preview belongs to another user. Generate your own preview.")
    preview_data = cache.get(data["preview_key"]) if "preview_key" in data else data
    if not preview_data:
        raise PreviewUnavailable("This preview is missing, expired, or invalid. Generate a new preview.")
    with transaction.atomic():
        # Serialize applies and reject changes made since the user reviewed the data.
        for model in (Taxon, Identification, FieldSlip):
            list(model.objects.select_for_update().order_by("pk").values_list("pk", flat=True))
        if data.get("fingerprint") != catalogue_fingerprint():
            raise PreviewUnavailable("The catalogue changed after this preview. Generate a new preview before applying.")
        taxa = {t.pk: t for t in Taxon.objects.select_related("accepted_taxon")}
        preview = _deserialize_preview(preview_data, taxa)
        return NowTaxonomySyncResult(preview, service._apply(preview))
