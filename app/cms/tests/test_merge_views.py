from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import models
from django.test import RequestFactory, SimpleTestCase, override_settings

from cms.merge.forms import FieldSelectionCandidate, FieldSelectionForm
from cms.merge.mixins import MergeMixin
from cms.merge.strategies import StrategyResolution
from cms.merge.views import FieldSelectionMergeView


class DummyMergeModel(MergeMixin):
    name = models.CharField(max_length=64)

    class Meta:
        app_label = "cms"
        managed = False

    def __str__(self):  # pragma: no cover - string representation for debugging
        return f"Dummy {getattr(self, 'pk', '?')}"


@dataclass
class DummyMergeResult:
    target: Any
    resolved_values: dict[str, Any]
    relation_actions: dict[str, Any]


@override_settings(MERGE_TOOL_FEATURE=True)
class FieldSelectionMergeViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

        self.target = DummyMergeModel(name="Target")
        self.target.pk = 1
        self.source = DummyMergeModel(name="Source")
        self.source.pk = 2

        self.form_field = DummyMergeModel._meta.get_field("name")

    def _build_candidates(self):
        return (
            [
                FieldSelectionCandidate.from_instance(
                    self.target, label="Target", role="target"
                ),
                FieldSelectionCandidate.from_instance(
                    self.source, label="Source", role="source"
                ),
            ],
            FieldSelectionCandidate.from_instance(self.target, label="Target", role="target"),
        )

    def _build_view(self):
        class TestView(FieldSelectionMergeView):
            def get_model(self_inner, request):
                return DummyMergeModel

            def get_mergeable_fields(self_inner, model):
                return [self.form_field]

            def get_candidates(self_inner, request, model):
                return self._build_candidates()

        return TestView.as_view()

    def _dummy_user(self):
        class DummyUser:
            is_staff = True
            is_authenticated = True
            pk = 99

        return DummyUser()

    def test_get_returns_field_options_for_candidates(self):
        request = self.factory.get(
            "/merge/field-selection/",
            {"model": "cms.DummyMergeModel", "target": 1, "candidates": "1,2"},
            HTTP_ACCEPT="application/json",
        )
        request.user = self._dummy_user()

        response = self._build_view()(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload["target"], self.target.pk)
        self.assertEqual(payload["candidates"], [str(self.target.pk), str(self.source.pk)])
        self.assertEqual(len(payload["fields"]), 1)

    def test_post_merges_selected_source_value_into_target(self):
        selection_field = FieldSelectionForm.selection_field_name("name")
        request = self.factory.post(
            "/merge/field-selection/",
            {"model": "cms.DummyMergeModel", "target": 1, "candidates": "1,2", selection_field: "2"},
            HTTP_ACCEPT="application/json",
        )
        request.user = self._dummy_user()

        dummy_result = DummyMergeResult(
            target=self.target,
            resolved_values={"name": {"value": "Source", "status": "updated"}},
            relation_actions={},
        )

        with (
            mock.patch("cms.merge.views.merge_records", return_value=dummy_result) as merge_mock,
            mock.patch("cms.merge.views.transaction.atomic"),
            mock.patch("django.contrib.messages.api.add_message"),
        ):
            response = self._build_view()(request)

        self.assertEqual(response.status_code, 200)
        merge_mock.assert_called_once()
        payload = json.loads(response.content.decode())
        self.assertEqual(payload["target_id"], self.target.pk)

    def test_post_serialises_model_values_in_json_response(self):
        selection_field = FieldSelectionForm.selection_field_name("name")
        request = self.factory.post(
            "/merge/field-selection/",
            {"model": "cms.DummyMergeModel", "target": 1, "candidates": "1,2", selection_field: "2"},
            HTTP_ACCEPT="application/json",
        )
        request.user = self._dummy_user()

        dummy_result = DummyMergeResult(
            target=self.target,
            resolved_values={"owner": StrategyResolution(value=request.user)},
            relation_actions={"owners": [request.user]},
        )

        with (
            mock.patch("cms.merge.views.merge_records", return_value=dummy_result),
            mock.patch("cms.merge.views.transaction.atomic"),
            mock.patch("django.contrib.messages.api.add_message"),
        ):
            response = self._build_view()(request)

        payload = json.loads(response.content.decode())
        self.assertEqual(payload["resolved_fields"]["owner"]["value"], request.user.pk)
        self.assertEqual(payload["relation_actions"]["owners"], [request.user.pk])

    def test_post_serialises_django_user_instances_in_json_response(self):
        selection_field = FieldSelectionForm.selection_field_name("name")
        request = self.factory.post(
            "/merge/field-selection/",
            {"model": "cms.DummyMergeModel", "target": 1, "candidates": "1,2", selection_field: "2"},
            HTTP_ACCEPT="application/json",
        )

        user_model = get_user_model()
        auth_user = user_model(username="auth-user", is_staff=True, is_superuser=True)
        auth_user.pk = 777
        request.user = auth_user

        dummy_result = DummyMergeResult(
            target=self.target,
            resolved_values={"owner": StrategyResolution(value=request.user)},
            relation_actions={"owners": [request.user]},
        )

        with (
            mock.patch("cms.merge.views.merge_records", return_value=dummy_result),
            mock.patch("cms.merge.views.transaction.atomic"),
            mock.patch("django.contrib.messages.api.add_message"),
        ):
            response = self._build_view()(request)

        payload = json.loads(response.content.decode())
        self.assertEqual(payload["resolved_fields"]["owner"]["value"], request.user.pk)
        self.assertEqual(payload["relation_actions"]["owners"], [request.user.pk])

    def test_post_serialises_date_values_in_json_response(self):
        selection_field = FieldSelectionForm.selection_field_name("name")
        request = self.factory.post(
            "/merge/field-selection/",
            {"model": "cms.DummyMergeModel", "target": 1, "candidates": "1,2", selection_field: "2"},
            HTTP_ACCEPT="application/json",
        )
        request.user = self._dummy_user()

        dummy_result = DummyMergeResult(
            target=self.target,
            resolved_values={"collected_at": StrategyResolution(value=date(2024, 1, 2))},
            relation_actions={},
        )

        with (
            mock.patch("cms.merge.views.merge_records", return_value=dummy_result),
            mock.patch("cms.merge.views.transaction.atomic"),
            mock.patch("django.contrib.messages.api.add_message"),
        ):
            response = self._build_view()(request)

        payload = json.loads(response.content.decode())
        self.assertEqual(payload["resolved_fields"]["collected_at"]["value"], "2024-01-02")

