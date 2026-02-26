from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from cms.models import (
    Accession,
    AccessionReference,
    Collection,
    Comment,
    Locality,
    Reference,
    Subject,
)


pytestmark = pytest.mark.django_db


class AccessionDetailTemplateTests(TestCase):
    def setUp(self):
        self.creator = get_user_model().objects.create_user(
            username="creator", password="pass"
        )
        self.patcher = patch("cms.models.get_current_user", return_value=self.creator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Collection description"
        )
        self.locality = Locality.objects.create(abbreviation="LOC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            is_published=True,
        )
        subject = Subject.objects.create(subject_name="General")
        self.comment = Comment.objects.create(
            specimen_no=self.accession,
            comment="Visible comment",
            subject=subject,
            status="N",
            comment_by="Tester",
        )
        self.reference = Reference.objects.create(
            title="Test Reference",
            first_author="Author",
            year="2024",
            citation="Author 2024",
        )
        AccessionReference.objects.create(
            accession=self.accession,
            reference=self.reference,
            page="12",
        )
        self.user = get_user_model().objects.create_user(
            username="viewer", password="pass"
        )

    def test_comments_section_hidden_for_anonymous_users(self):
        response = self.client.get(reverse("accession_detail", args=[self.accession.pk]))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn("accession-comments-heading", body)
        self.assertNotIn(self.comment.comment, body)

    def test_comments_section_visible_for_authenticated_users(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accession_detail", args=[self.accession.pk]))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("accession-comments-heading", body)
        self.assertIn(self.comment.comment, body)

    def test_reference_titles_link_to_reference_detail_page(self):
        response = self.client.get(reverse("accession_detail", args=[self.accession.pk]))

        self.assertEqual(response.status_code, 200)
        reference_url = self.reference.get_absolute_url()
        body = response.content.decode()
        self.assertIn(f'href="{reference_url}"', body)
        self.assertIn(self.reference.title, body)


class LocalityDetailHeadingTests(TestCase):
    def setUp(self):
        self.creator = get_user_model().objects.create_user(
            username="creator", password="pass"
        )
        self.patcher = patch("cms.models.get_current_user", return_value=self.creator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        collection = Collection.objects.create(
            abbreviation="COL", description="Collection description"
        )
        self.locality = Locality.objects.create(abbreviation="LCL", name="Locality")
        self.published_accession = Accession.objects.create(
            collection=collection,
            specimen_prefix=self.locality,
            specimen_no=10,
            is_published=True,
        )
        self.user = get_user_model().objects.create_user(
            username="member", password="pass"
        )

    def test_heading_for_anonymous_users(self):
        response = self.client.get(reverse("locality_detail", args=[self.locality.pk]))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Associated published accessions", body)
        self.assertNotIn("Associated accessions", body)

    def test_heading_for_authenticated_users(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("locality_detail", args=[self.locality.pk]))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Associated accessions", body)
        self.assertNotIn("Associated published accessions", body)
