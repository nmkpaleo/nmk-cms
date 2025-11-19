"""Regression tests for the customized django-allauth templates."""
from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.sites.models import Site
from django.test import Client
from django.urls import reverse

from allauth.socialaccount.models import SocialApp


pytestmark = pytest.mark.django_db


@pytest.fixture()
def orcid_social_app(db):
    """Ensure an ORCID social application exists for template tests."""
    site, _ = Site.objects.get_or_create(
        id=settings.SITE_ID,
        defaults={"domain": "example.com", "name": "example.com"},
    )
    social_app, _ = SocialApp.objects.get_or_create(
        provider="orcid",
        defaults={
            "name": "ORCID",
            "client_id": "test-client-id",
            "secret": "test-secret",
        },
    )
    social_app.sites.set([site])
    return social_app


def test_login_template_renders_w3_layout(orcid_social_app):
    """The login view should render the shared W3.CSS auth layout with imagery."""
    client = Client()
    response = client.get(reverse("account_login"))

    assert response.status_code == 200
    body = response.content.decode()

    assert "w3-container w3-padding-64 w3-sand" in body
    assert "images/animal_skull.png" in body
    assert "fa-solid fa-shield-halved" in body


def test_login_template_includes_orcid_cta(orcid_social_app):
    """Verify that the ORCID button renders with the branded image and text."""
    client = Client()
    response = client.get(reverse("account_login"))

    assert response.status_code == 200
    body = response.content.decode()

    assert "Sign in with ORCID" in body
    assert "images/orcid-logo.png" in body
    assert "w3-button w3-green" in body
