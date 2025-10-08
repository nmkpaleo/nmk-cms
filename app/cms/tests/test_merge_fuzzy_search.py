from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection, models
from django.test import TransactionTestCase
from django.test.utils import isolate_apps
from django.urls import reverse

from cms.merge.mixins import MergeMixin
from cms.merge.registry import MERGE_REGISTRY, register_merge_rules


@isolate_apps("cms")
class MergeCandidateAPITests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class Candidate(MergeMixin):
            name = models.CharField(max_length=64)
            city = models.CharField(max_length=64)

            class Meta:
                app_label = "cms"

            def __str__(self) -> str:
                return self.name

        cls.Model = Candidate

        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.create_model(Candidate)
        finally:
            connection.enable_constraint_checking()

        cls._previous_registry_entry = MERGE_REGISTRY.get(Candidate)
        register_merge_rules(Candidate)
        cls.UserModel = get_user_model()

    @classmethod
    def tearDownClass(cls):
        MERGE_REGISTRY.pop(cls.Model, None)
        if cls._previous_registry_entry is not None:
            MERGE_REGISTRY[cls.Model] = cls._previous_registry_entry
        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.delete_model(cls.Model)
        finally:
            connection.enable_constraint_checking()
        super().tearDownClass()

    def setUp(self):
        self.best = self.Model.objects.create(name="Alpha Beta", city="Nairobi")
        self.partial = self.Model.objects.create(name="Alpha Gamma", city="Nakuru")
        self.low = self.Model.objects.create(name="Delta Epsilon", city="Mombasa")
        self.model_label = f"{self.Model._meta.app_label}.{self.Model._meta.model_name}"
        self.url = reverse("merge_candidate_search")

    def test_requires_staff_permissions(self):
        params = {"model_label": self.model_label, "query": "Alpha", "fields": "name"}
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

        user = self.UserModel.objects.create_user(username="regular", password="pass", is_staff=False)
        self.client.force_login(user)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_threshold_filters_candidates(self):
        staff = self.UserModel.objects.create_user(username="staff", password="pass", is_staff=True)
        self.client.force_login(staff)

        params = {
            "model_label": self.model_label,
            "query": "Alpha Beta",
            "fields": "name",
            "threshold": "70",
        }
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([result["candidate"]["pk"] for result in payload["results"]], [self.best.pk])

        params["threshold"] = "50"
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [result["candidate"]["pk"] for result in payload["results"]],
            [self.best.pk, self.partial.pk],
        )
