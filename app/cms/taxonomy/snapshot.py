"""Signed, user-bound preview snapshots; apply never refetches remote sources."""
import hashlib
import json
from dataclasses import asdict

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


def catalogue_fingerprint():
    data = {
        "taxa": list(Taxon.objects.order_by("pk").values()),
        "identifications": list(Identification.objects.order_by("pk").values_list(
            "pk", "taxon_verbatim", "taxon", "taxon_record_id")),
        "field_slips": list(FieldSlip.objects.order_by("pk").values_list("pk", "verbatim_taxon")),
    }
    return hashlib.sha256(json.dumps(data, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def sign_preview(preview, user_id, fingerprint):
    data = {"user": user_id, "fingerprint": fingerprint,
            "source_version": preview.source_version,
            "import_source": getattr(preview, "import_source", "NOW_GBIF"),
            "accepted_to_create": [asdict(r) for r in preview.accepted_to_create],
            "synonyms_to_create": [asdict(r) for r in preview.synonyms_to_create],
            "to_deactivate": [t.pk for t in preview.to_deactivate],
            "issues": [asdict(i) for i in preview.issues]}
    for category in ("accepted_to_update", "synonyms_to_update"):
        data[category] = [{"pk": u.instance.pk, "record": asdict(u.record), "changes": u.changes}
                          for u in getattr(preview, category)]
    return signing.dumps(data, salt=SALT, compress=True)


def apply_signed_preview(token, user_id, service):
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature as exc:
        raise PreviewUnavailable("This preview is missing, expired, or invalid. Generate a new preview.") from exc
    if data["user"] != user_id:
        raise PreviewUnavailable("This preview belongs to another user. Generate your own preview.")
    with transaction.atomic():
        # Serialize applies and reject changes made since the user reviewed the data.
        for model in (Taxon, Identification, FieldSlip):
            list(model.objects.select_for_update().order_by("pk").values_list("pk", flat=True))
        if data["fingerprint"] != catalogue_fingerprint():
            raise PreviewUnavailable("The catalogue changed after this preview. Generate a new preview before applying.")
        taxa = {t.pk: t for t in Taxon.objects.select_related("accepted_taxon")}
        preview = SyncPreview(
            accepted_to_create=[AcceptedRecord(**r) for r in data["accepted_to_create"]],
            synonyms_to_create=[SynonymRecord(**r) for r in data["synonyms_to_create"]],
            accepted_to_update=[AcceptedUpdate(taxa[u["pk"]], AcceptedRecord(**u["record"]), u["changes"])
                                for u in data["accepted_to_update"]],
            synonyms_to_update=[SynonymUpdate(taxa[u["pk"]], SynonymRecord(**u["record"]), u["changes"])
                                for u in data["synonyms_to_update"]],
            to_deactivate=[taxa[pk] for pk in data["to_deactivate"]],
            issues=[SyncIssue(**i) for i in data["issues"]],
            source_version=data["source_version"], import_source=data["import_source"],
        )
        return NowTaxonomySyncResult(preview, service._apply(preview))
