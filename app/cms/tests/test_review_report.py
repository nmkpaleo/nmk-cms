from __future__ import annotations

from datetime import datetime

import pytest
from crum import set_current_user
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from cms.models import Accession, Collection, Locality, Media

pytestmark = pytest.mark.django_db


def _manager_user(django_user_model, username="manager"):
    user = django_user_model.objects.create_user(username=username, password="x")
    group, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(group)
    return user


def _reviewer(django_user_model, username):
    return django_user_model.objects.create_user(username=username, password="x")


def _reviewed_at(year, month, day, hour=9):
    return timezone.make_aware(datetime(year, month, day, hour, 0))


def _accession(user, number=1):
    set_current_user(user)
    try:
        collection = Collection.objects.create(abbreviation=f"T{number}", description=f"Test {number}")
        locality = Locality.objects.create(abbreviation=f"L{number}", name=f"Locality {number}")
        return Accession.objects.create(collection=collection, specimen_prefix=locality, specimen_no=number)
    finally:
        set_current_user(None)


def _media(user, **kwargs):
    set_current_user(user)
    try:
        return Media.objects.create(**kwargs)
    finally:
        set_current_user(None)


def test_review_report_generates_intern_report_for_custom_range(client, django_user_model):
    manager = _manager_user(django_user_model)
    mike = _reviewer(django_user_model, "Mike")
    other_reviewer = _reviewer(django_user_model, "Amina")
    accession = _accession(manager)
    _media(
        manager,
        media_location="uploads/review-1.jpg",
        accession=accession,
        intern_checked_by=mike,
        intern_checked_on=_reviewed_at(2026, 10, 1),
        rows_rearranged=True,
    )
    _media(
        manager,
        media_location="uploads/review-2.jpg",
        accession=accession,
        intern_checked_by=mike,
        intern_checked_on=_reviewed_at(2026, 10, 7),
    )
    _media(
        manager,
        media_location="uploads/review-3.jpg",
        accession=accession,
        intern_checked_by=other_reviewer,
        intern_checked_on=_reviewed_at(2026, 10, 3),
    )

    client.force_login(manager)
    response = client.get(
        reverse("review_report"),
        {
            "generate": "1",
            "role": "intern",
            "reviewer": str(mike.pk),
            "period": "custom",
            "start_date": "2026-10-01",
            "end_date": "2026-10-07",
        },
    )

    assert response.status_code == 200
    assert response.context["summary"]["reviewed_records"] == 2
    assert response.context["summary"]["active_days"] == 2
    assert response.context["summary"]["average_per_day"] == 1
    assert response.context["summary"]["records_rearranged"] == 1
    content = response.content.decode()
    assert "Intern Review Report: Mike" in content
    assert "Reviews per day" in content
    assert "Summary" in content
    assert "Accession ID" not in content
    assert "Individual review records" not in content


def test_review_report_generates_expert_report(client, django_user_model):
    manager = _manager_user(django_user_model, "manager2")
    expert = _reviewer(django_user_model, "Expert")
    accession = _accession(manager, 2)
    _media(
        manager,
        media_location="uploads/expert-review.jpg",
        accession=accession,
        expert_checked_by=expert,
        expert_checked_on=_reviewed_at(2026, 9, 30),
    )

    client.force_login(manager)
    response = client.get(
        reverse("review_report"),
        {
            "generate": "1",
            "role": "expert",
            "reviewer": str(expert.pk),
            "period": "all",
        },
    )

    assert response.status_code == 200
    assert response.context["summary"]["role_label"] == "Expert"
    assert response.context["summary"]["reviewed_records"] == 1
    assert response.context["summary"]["active_days"] == 1
    assert "Expert Review Report: Expert" in response.content.decode()


def test_review_report_requires_collection_manager(client, django_user_model):
    url = reverse("review_report")
    response = client.get(url)
    assert response.status_code == 302
    assert response.url == f"{reverse('account_login')}?next={url}"

    user = django_user_model.objects.create_user(username="regular", password="x")
    client.force_login(user)
    response = client.get(url)
    assert response.status_code == 302
    assert response.url == f"{reverse('account_login')}?next={url}"
