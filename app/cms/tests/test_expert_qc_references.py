import copy
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.conf import settings
from django.urls import reverse
from django.test import Client
from django.test.utils import setup_test_environment, teardown_test_environment
from crum import impersonate

from cms.models import Collection, Locality, Media

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture(autouse=True)
def apply_migrations():
    call_command("migrate", run_syncdb=True, verbosity=0)


@pytest.fixture(autouse=True)
def allow_test_host():
    settings.ALLOWED_HOSTS = list(
        {"testserver", "localhost", *settings.ALLOWED_HOSTS}
    )


@pytest.fixture(autouse=True)
def test_environment():
    setup_test_environment()
    yield
    teardown_test_environment()


def _create_expert_user():
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username=f"expert-{uuid.uuid4()}",
        email="expert@example.com",
        password="password123",
    )
    group, _ = Group.objects.get_or_create(name="Curators")
    user.groups.add(group)
    return user


def _create_collection_and_locality(user):
    collection_abbr = uuid.uuid4().hex[:4].upper()
    locality_abbr = uuid.uuid4().hex[:2].upper()

    with impersonate(user):
        collection = Collection.objects.create(
            abbreviation=collection_abbr,
            description=f"Test Collection {collection_abbr}",
        )
        locality = Locality.objects.create(
            abbreviation=locality_abbr, name=f"Test Locality {locality_abbr}"
        )
    return collection, locality


def _build_media_with_references(user, collection, locality, references):
    accession_payload = {
        "collection_abbreviation": {"interpreted": collection.abbreviation},
        "specimen_prefix_abbreviation": {"interpreted": locality.abbreviation},
        "specimen_no": {"interpreted": 1},
        "type_status": {"interpreted": None},
        "comment": {"interpreted": ""},
        "references": copy.deepcopy(references),
    }
    ocr_data = {
        "_original_snapshot": {"accessions": [copy.deepcopy(accession_payload)]},
        "accessions": [copy.deepcopy(accession_payload)],
    }

    with impersonate(user):
        return Media.objects.create(
            media_location="uploads/test-reference.jpg",
            file_name="test-reference.jpg",
            qc_status=Media.QCStatus.PENDING_EXPERT,
            ocr_status=Media.OCRStatus.COMPLETED,
            ocr_data=ocr_data,
        )


def test_expert_qc_reference_delete_updates_payload(client):
    expert_user = _create_expert_user()
    collection, locality = _create_collection_and_locality(expert_user)
    references = [
        {
            "_ref_id": "ref-0",
            "reference_first_author": {"interpreted": "Alpha"},
            "reference_title": {"interpreted": "First"},
            "reference_year": {"interpreted": "2000"},
            "page": {"interpreted": "10"},
        },
        {
            "_ref_id": "ref-1",
            "reference_first_author": {"interpreted": "Beta"},
            "reference_title": {"interpreted": "Second"},
            "reference_year": {"interpreted": "2001"},
            "page": {"interpreted": "20"},
        },
    ]
    media = _build_media_with_references(expert_user, collection, locality, references)
    client.force_login(expert_user)

    url = reverse("media_expert_qc", args=[media.uuid])
    response = client.get(url)
    assert response.status_code == 200

    post_data = {
        "action": "save",
        "qc_comment": "",
        "accession-collection": str(collection.pk),
        "accession-specimen_prefix": str(locality.pk),
        "accession-specimen_no": "1",
        "accession-accessioned_by": str(expert_user.pk),
        "accession-type_status": "",
        "accession-comment": "",
        "row-TOTAL_FORMS": "0",
        "row-INITIAL_FORMS": "0",
        "row-MIN_NUM_FORMS": "0",
        "row-MAX_NUM_FORMS": "1000",
        "ident-TOTAL_FORMS": "0",
        "ident-INITIAL_FORMS": "0",
        "ident-MIN_NUM_FORMS": "0",
        "ident-MAX_NUM_FORMS": "1000",
        "specimen-TOTAL_FORMS": "0",
        "specimen-INITIAL_FORMS": "0",
        "specimen-MIN_NUM_FORMS": "0",
        "specimen-MAX_NUM_FORMS": "1000",
        "reference-TOTAL_FORMS": "2",
        "reference-INITIAL_FORMS": "2",
        "reference-MIN_NUM_FORMS": "0",
        "reference-MAX_NUM_FORMS": "1000",
        "reference-0-ref_id": "ref-0",
        "reference-0-order": "0",
        "reference-0-first_author": "Alpha",
        "reference-0-title": "First",
        "reference-0-year": "2000",
        "reference-0-page": "10",
        "reference-0-DELETE": "on",
        "reference-1-ref_id": "ref-1",
        "reference-1-order": "1",
        "reference-1-first_author": "Beta",
        "reference-1-title": "Second",
        "reference-1-year": "2001",
        "reference-1-page": "20",
        "fieldslip-TOTAL_FORMS": "0",
        "fieldslip-INITIAL_FORMS": "0",
        "fieldslip-MIN_NUM_FORMS": "0",
        "fieldslip-MAX_NUM_FORMS": "1000",
    }

    post_response = client.post(url, data=post_data)

    assert post_response.status_code == 302

    media.refresh_from_db()
    updated_references = (
        (media.ocr_data or {})
        .get("accessions", [{}])[0]
        .get("references", [])
    )
    assert len(updated_references) == 1
    remaining_reference = updated_references[0]
    assert remaining_reference.get("reference_first_author", {}).get(
        "interpreted"
    ) == "Beta"
    assert remaining_reference.get("reference_title", {}).get("interpreted") == "Second"
    assert remaining_reference.get("reference_year", {}).get("interpreted") == "2001"
    assert remaining_reference.get("page", {}).get("interpreted") == "20"


def test_expert_qc_reference_formset_can_delete_enabled(client):
    expert_user = _create_expert_user()
    collection, locality = _create_collection_and_locality(expert_user)
    media = _build_media_with_references(
        expert_user,
        collection,
        locality,
        [
            {
                "_ref_id": "ref-0",
                "reference_first_author": {"interpreted": "Gamma"},
                "reference_title": {"interpreted": "Third"},
                "reference_year": {"interpreted": "2002"},
                "page": {"interpreted": "30"},
            }
        ],
    )
    client.force_login(expert_user)

    response = client.get(reverse("media_expert_qc", args=[media.uuid]))

    assert response.status_code == 200
    reference_formset = response.context["reference_formset"]
    assert reference_formset.can_delete is True
    assert reference_formset.forms
    delete_field = reference_formset.forms[0].fields.get("DELETE")
    assert delete_field is not None
    assert delete_field.widget.is_hidden
