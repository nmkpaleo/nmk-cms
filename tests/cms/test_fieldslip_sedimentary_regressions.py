from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from cms.models import (
    CollectionMethod,
    FieldSlip,
    FossilGroup,
    GrainSize,
    PreservationState,
    SedimentaryFeature,
)


pytestmark = pytest.mark.usefixtures("django_db_setup")


class FieldSlipSedimentaryRegressionTests(TestCase):
    def setUp(self):
        self.creator = get_user_model().objects.create_user(
            username="creator", password="pass"
        )
        self.current_user_patcher = patch(
            "cms.models.get_current_user", return_value=self.creator
        )
        self.current_user_patcher.start()
        self.addCleanup(self.current_user_patcher.stop)

        self.collection_managers, _ = Group.objects.get_or_create(
            name="Collection Managers"
        )
        self.manager = get_user_model().objects.create_user(
            username="manager", password="pass"
        )
        self.manager.groups.add(self.collection_managers)

        self.sedimentary_feature = SedimentaryFeature.objects.create(
            name="Cross bedding",
            code="CB",
            category="sedimentary",
        )
        self.fossil_group = FossilGroup.objects.create(name="Mammalia")
        self.preservation_state = PreservationState.objects.create(name="Fragmented")
        self.collection_method = CollectionMethod.objects.create(name="Screen wash")
        self.grain_size = GrainSize.objects.create(name="Fine")

        self.fieldslip = FieldSlip.objects.create(
            field_number="FS-685",
            collector="Tester",
            verbatim_taxon="Pan",
            verbatim_element="Molar",
            collection_position="in_situ",
            matrix_association="attached",
            surface_exposure=True,
            matrix_grain_size=self.grain_size,
        )
        self.fieldslip.sedimentary_features.add(self.sedimentary_feature)
        self.fieldslip.fossil_groups.add(self.fossil_group)
        self.fieldslip.preservation_states.add(self.preservation_state)
        self.fieldslip.recommended_methods.add(self.collection_method)

        self.other_fieldslip = FieldSlip.objects.create(
            field_number="FS-999",
            collector="Other",
            verbatim_taxon="Pan",
            verbatim_element="Canine",
        )

    def test_detail_renders_sedimentary_section_before_related_accessions(self):
        response = self.client.get(reverse("fieldslip_detail", args=[self.fieldslip.pk]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Sedimentary context", content)
        self.assertIn("Related accessions", content)
        self.assertLess(content.index("Sedimentary context"), content.index("Related accessions"))

    def test_edit_persists_sedimentary_fields(self):
        self.client.force_login(self.manager)

        payload = {
            "field_number": "FS-685",
            "discoverer": "Discoverer A",
            "collector": "Collector B",
            "collection_date": "2024-08-01",
            "verbatim_locality": "Locality 1",
            "verbatim_taxon": "Panthera",
            "verbatim_element": "M1",
            "verbatim_horizon": "Horizon X",
            "aerial_photo": "AP-1",
            "verbatim_latitude": "-1.0",
            "verbatim_longitude": "36.0",
            "verbatim_SRS": "WGS84",
            "verbatim_coordinate_system": "Geographic",
            "verbatim_elevation": "1200",
            "sedimentary_features": [str(self.sedimentary_feature.pk)],
            "fossil_groups": [str(self.fossil_group.pk)],
            "preservation_states": [str(self.preservation_state.pk)],
            "recommended_methods": [str(self.collection_method.pk)],
            "collection_position": "ex_situ",
            "matrix_association": "loose",
            "surface_exposure": "true",
            "matrix_grain_size": str(self.grain_size.pk),
        }

        response = self.client.post(
            reverse("fieldslip_edit", args=[self.fieldslip.pk]),
            payload,
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.fieldslip.refresh_from_db()
        self.assertEqual(self.fieldslip.collection_position, "ex_situ")
        self.assertEqual(self.fieldslip.matrix_association, "loose")
        self.assertTrue(self.fieldslip.surface_exposure)
        self.assertEqual(self.fieldslip.matrix_grain_size, self.grain_size)
        self.assertQuerySetEqual(
            self.fieldslip.sedimentary_features.order_by("pk"),
            [self.sedimentary_feature],
            transform=lambda obj: obj,
        )
        self.assertQuerySetEqual(
            self.fieldslip.fossil_groups.order_by("pk"),
            [self.fossil_group],
            transform=lambda obj: obj,
        )

    def test_list_filter_uses_sedimentary_criteria_without_duplicate_rows(self):
        self.client.force_login(self.manager)

        query = {
            "sedimentary_features": [str(self.sedimentary_feature.pk)],
            "fossil_groups": [str(self.fossil_group.pk)],
            "preservation_states": [str(self.preservation_state.pk)],
            "recommended_methods": [str(self.collection_method.pk)],
            "collection_position": "in_situ",
            "matrix_association": "attached",
            "surface_exposure": "true",
            "matrix_grain_size": str(self.grain_size.pk),
        }

        response = self.client.get(reverse("fieldslip_list"), query)

        self.assertEqual(response.status_code, 200)
        page_objects = list(response.context["fieldslips"])
        self.assertEqual([obj.pk for obj in page_objects], [self.fieldslip.pk])
        self.assertEqual(len({obj.pk for obj in page_objects}), len(page_objects))
        content = response.content.decode()
        self.assertIn("Sedimentary filters", content)
        self.assertIn("FS-685", content)
        self.assertNotIn("FS-999", content)
