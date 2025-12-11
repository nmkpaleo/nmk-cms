import types
import uuid

import pytest
from django import forms
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse
from crum import impersonate

from cms.merge.forms import ElementFieldSelectionForm, FieldSelectionCandidate
from cms.models import Element

call_command("migrate", run_syncdb=True, verbosity=0)


@pytest.mark.django_db
def test_element_merge_template_renders_filters_and_selection():
    rf = RequestFactory()
    request = rf.get("/merge/elements/")
    request.user = AnonymousUser()

    user = get_user_model().objects.create_user(username=f"mergeuser-{uuid.uuid4()}")

    with impersonate(user):
        parent = Element.objects.create(name="Skull")
        child_one = Element.objects.create(name="Mandible", parent_element=parent)
        child_two = Element.objects.create(name="Maxilla", parent_element=parent)

    class DummyFilter(forms.Form):
        name = forms.CharField(label="Name", required=False)
        parent_element = forms.CharField(label="Parent", required=False)

    filterset = types.SimpleNamespace(form=DummyFilter())
    page_obj = Paginator([parent, child_one, child_two], 2).page(1)

    html = render_to_string(
        "merge/element_merge.html",
        {
            "filter": filterset,
            "page_obj": page_obj,
            "confirm_url": reverse("merge:merge_element_field_selection"),
            "cancel_url": "/dashboard/",
        },
        request=request,
    )

    assert "Merge elements" in html
    assert "Element selection table" in html
    assert "Name" in html
    assert f"id_target_{parent.pk}" in html
    assert f"id_source_{child_one.pk}" in html
    assert "w3-pagination" in html


@pytest.mark.django_db
def test_element_merge_confirm_template_renders_field_selection_table():
    rf = RequestFactory()
    request = rf.get("/merge/elements/confirm/")
    request.user = AnonymousUser()

    user = get_user_model().objects.create_user(username=f"mergeapprover-{uuid.uuid4()}")

    with impersonate(user):
        target = Element.objects.create(name="Ulna")
        source = Element.objects.create(name="Radius")

    candidates = [
        FieldSelectionCandidate.from_instance(target, role="target"),
        FieldSelectionCandidate.from_instance(source, role="source"),
    ]
    form = ElementFieldSelectionForm(
        model=Element,
        merge_fields=ElementFieldSelectionForm.get_mergeable_fields(Element),
        candidates=candidates,
    )

    html = render_to_string(
        "merge/element_merge_confirm.html",
        {
            "form": form,
            "target": target,
            "sources": [source],
            "target_id": target.pk,
            "candidate_ids": f"{target.pk},{source.pk}",
            "action_url": reverse("merge:merge_element_field_selection"),
            "cancel_url": "/merge/elements/",
        },
        request=request,
    )

    assert "Review selections" in html
    assert target.name in html
    assert source.name in html
    assert "Apply selections" in html
    assert "No mergeable fields available" not in html
