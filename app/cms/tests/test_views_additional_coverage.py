from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.http import QueryDict
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from cms.views import MergeCandidateAPIView, is_collection_manager


@pytest.mark.django_db
class TestViewCoverageAdditions:
    def test_is_collection_manager_requires_auth_and_group(self, django_user_model):
        assert is_collection_manager(AnonymousUser()) is False

        user = django_user_model.objects.create_user(username="u1", password="x")
        assert is_collection_manager(user) is False

        group = Group.objects.create(name="Collection Managers")
        user.groups.add(group)
        assert is_collection_manager(user) is True

    def test_media_report_empty_dataset_message(self, client, django_user_model):
        user = django_user_model.objects.create_user(username="manager", password="x")
        user.groups.add(Group.objects.create(name="Collection Managers"))
        client.force_login(user)

        with patch("cms.views.Media.objects.values", return_value=[]):
            response = client.get(reverse("media_report"))

        assert response.status_code == 200
        assert "No media data available for reporting yet." in response.content.decode()

    def test_accession_distribution_report_no_data_message(self, client, django_user_model):
        user = django_user_model.objects.create_user(username="manager2", password="x")
        user.groups.add(Group.objects.create(name="Collection Managers"))
        client.force_login(user)

        class _EmptyQS:
            def values(self, *_args, **_kwargs):
                return self

            def annotate(self, *_args, **_kwargs):
                return self

            def order_by(self, *_args, **_kwargs):
                return []

        with patch("cms.views.Accession.objects", _EmptyQS()):
            response = client.get(reverse("accession_distribution_report"))

        assert response.status_code == 200
        assert "No accession data available yet." in response.content.decode()


def _rf_get(path: str, query: dict[str, str] | None = None, **headers):
    rf = RequestFactory()
    return rf.get(path, data=query or {}, **headers)


class _FakeMergeModel:
    class _Meta:
        app_label = "cms"
        model_name = "fake"
        verbose_name = "fake"

        concrete_fields = []

        @staticmethod
        def get_field(name):
            if name == "created_on":
                from django.db import models

                return models.DateTimeField()
            raise Exception("missing")

    _meta = _Meta()



class TestMergeCandidateAPIViewHelpers:
    def setup_method(self):
        self.view = MergeCandidateAPIView()

    def test_parse_threshold_and_positive_int_helpers(self):
        assert self.view._parse_threshold(None) == 75.0
        assert self.view._parse_threshold("bad") is None
        assert self.view._parse_threshold("120") == 100.0
        assert self.view._parse_threshold("-5") == 0.0

        assert self.view._parse_positive_int(None, default=1) == 1
        assert self.view._parse_positive_int("5", default=1) == 5
        assert self.view._parse_positive_int("0", default=1) is None

    def test_wants_json_and_query_param_building(self):
        req = _rf_get("/merge/search", {"format": "json", "page": "2", "q": "abc"})
        assert self.view._wants_json(req) is True
        assert "page=" not in self.view._build_query_params(req)

        req2 = _rf_get("/merge/search", {"q": "abc"}, HTTP_ACCEPT="application/json")
        assert self.view._wants_json(req2) is True

        req3 = _rf_get("/merge/search", {"q": "abc"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert self.view._wants_json(req3) is True

    def test_parse_datetime_supports_date_only_and_invalid(self):
        parsed = self.view._parse_datetime("2025-01-10", end_of_day=False)
        assert parsed is not None and timezone.is_aware(parsed)

        parsed_end = self.view._parse_datetime("2025-01-10", end_of_day=True)
        assert parsed_end is not None and parsed_end.date().isoformat() == "2025-01-10"

        assert self.view._parse_datetime("not-a-date", end_of_day=False) is None

    def test_extract_fields_prefers_explicit_query_param(self):
        req = _rf_get("/merge/search", {"fields": "name, code"})
        fields = self.view._extract_fields(req, _FakeMergeModel)
        assert fields == ["name", "code"]

    def test_build_queryset_validates_date_field_and_range(self):
        class _QS:
            def __init__(self):
                self.kwargs = None

            def all(self):
                return self

            def filter(self, **kwargs):
                self.kwargs = kwargs
                return self

        model = _FakeMergeModel
        model._default_manager = _QS()

        req = _rf_get(
            "/merge/search",
            {
                "date_field": "created_on",
                "date_after": "2025-01-01",
                "date_before": "2025-01-05",
            },
        )
        qs = self.view._build_queryset(req, model)
        assert "created_on__gte" in qs.kwargs
        assert "created_on__lte" in qs.kwargs
