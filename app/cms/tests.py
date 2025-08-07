from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cms.models import (
    Accession,
    AccessionNumberSeries,
    AccessionRow,
    Collection,
    Locality,
    Preparation,
    PreparationStatus,
)
from cms.utils import generate_accessions_from_series


class GenerateAccessionsFromSeriesTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.series_user = User.objects.create_user(
            username="series_user", password="pass"
        )
        self.creator = User.objects.create_user(
            username="creator", password="pass"
        )

        # Patch get_current_user used in BaseModel to bypass authentication
        self.patcher = patch("cms.models.get_current_user", return_value=self.creator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.series = AccessionNumberSeries.objects.create(
            user=self.series_user,
            start_from=1,
            end_at=10,
            current_number=1,
            is_active=True,
        )

    def test_generate_accessions_creates_records_and_increments_series(self):
        accessions = generate_accessions_from_series(
            self.series_user,
            count=3,
            collection=self.collection,
            specimen_prefix=self.locality,
            creator_user=self.creator,
        )

        self.series.refresh_from_db()
        self.assertEqual(self.series.current_number, 4)
        self.assertEqual(Accession.objects.count(), 3)
        numbers = list(Accession.objects.values_list("specimen_no", flat=True))
        self.assertEqual(numbers, [1, 2, 3])

        for acc in accessions:
            self.assertEqual(acc.collection, self.collection)
            self.assertEqual(acc.specimen_prefix, self.locality)
            self.assertEqual(acc.accessioned_by, self.series_user)

    def test_generate_accessions_raises_without_active_series(self):
        self.series.is_active = False
        self.series.save()

        with self.assertRaisesMessage(
            ValueError,
            f"No active accession number series found for user {self.series_user.username}.",
        ):
            generate_accessions_from_series(
                self.series_user,
                count=1,
                collection=self.collection,
                specimen_prefix=self.locality,
                creator_user=self.creator,
            )


class PreparationUpdateViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.preparator = User.objects.create_user(
            username="prep", password="pass"
        )
        self.curator = User.objects.create_user(
            username="cur", password="pass"
        )
        self.other_curator = User.objects.create_user(
            username="cur2", password="pass"
        )

        self.curators_group = Group.objects.create(name="Curators")
        self.preparators_group = Group.objects.create(name="Preparators")
        self.curators_group.user_set.add(self.curator, self.other_curator)
        self.preparators_group.user_set.add(self.preparator)

        self.patcher = patch("cms.models.get_current_user", return_value=self.curator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.preparator,
        )
        self.accession_row = AccessionRow.objects.create(accession=self.accession)
        self.preparation = Preparation.objects.create(
            accession_row=self.accession_row,
            preparator=self.preparator,
            curator=self.curator,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.COMPLETED,
        )

    def test_curator_must_match_to_edit(self):
        self.client.login(username="cur2", password="pass")
        url = reverse("preparation_edit", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_curator_sees_only_approved_declined_choices(self):
        self.client.login(username="cur", password="pass")
        url = reverse("preparation_edit", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        choices = [c[0] for c in response.context["form"].fields["status"].choices]
        self.assertEqual(
            choices,
            [PreparationStatus.APPROVED, PreparationStatus.DECLINED],
        )

    def test_curator_cannot_set_invalid_status(self):
        self.client.login(username="cur", password="pass")
        url = reverse("preparation_edit", args=[self.preparation.pk])
        data = {
            "accession_row": self.accession_row.pk,
            "preparation_type": "cleaning",
            "preparator": self.preparator.pk,
            "started_on": "2023-01-01",
            "status": PreparationStatus.IN_PROGRESS,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response,
            "form",
            "status",
            "You can only set status to Approved or Declined.",
        )


class PreparationDetailViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.preparator = User.objects.create_user(
            username="prep", password="pass"
        )
        self.curator = User.objects.create_user(
            username="cur", password="pass"
        )
        self.other_curator = User.objects.create_user(
            username="cur2", password="pass"
        )

        self.curators_group = Group.objects.create(name="Curators")
        self.preparators_group = Group.objects.create(name="Preparators")
        self.curators_group.user_set.add(self.curator, self.other_curator)
        self.preparators_group.user_set.add(self.preparator)

        self.patcher = patch("cms.models.get_current_user", return_value=self.curator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.preparator,
        )
        self.accession_row = AccessionRow.objects.create(accession=self.accession)
        self.preparation = Preparation.objects.create(
            accession_row=self.accession_row,
            preparator=self.preparator,
            curator=self.curator,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.IN_PROGRESS,
        )

    def test_preparator_sees_edit_button(self):
        self.client.login(username="prep", password="pass")
        url = reverse("preparation_detail", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertContains(response, "Edit Preparation")

    def test_assigned_curator_sees_edit_button(self):
        self.client.login(username="cur", password="pass")
        url = reverse("preparation_detail", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertContains(response, "Edit Preparation")

    def test_unassigned_curator_does_not_see_edit_button(self):
        self.client.login(username="cur2", password="pass")
        url = reverse("preparation_detail", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertNotContains(response, "Edit Preparation")


class DashboardViewCuratorTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.preparator = User.objects.create_user(
            username="prep", password="pass"
        )
        self.curator = User.objects.create_user(
            username="cur", password="pass"
        )
        self.other_curator = User.objects.create_user(
            username="cur2", password="pass"
        )

        self.curators_group = Group.objects.create(name="Curators")
        self.preparators_group = Group.objects.create(name="Preparators")
        self.curators_group.user_set.add(self.curator, self.other_curator)
        self.preparators_group.user_set.add(self.preparator)

        self.patcher = patch("cms.models.get_current_user", return_value=self.curator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.preparator,
        )
        self.accession_row1 = AccessionRow.objects.create(accession=self.accession)
        self.accession_row2 = AccessionRow.objects.create(accession=self.accession)

        self.curator_prep = Preparation.objects.create(
            accession_row=self.accession_row1,
            preparator=self.preparator,
            curator=self.curator,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.COMPLETED,
        )
        self.other_curator_prep = Preparation.objects.create(
            accession_row=self.accession_row2,
            preparator=self.preparator,
            curator=self.other_curator,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.COMPLETED,
        )

    def test_curator_sees_only_their_completed_preparations(self):
        self.client.login(username="cur", password="pass")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["completed_preparations"]),
            [self.curator_prep],
        )


class DashboardViewCollectionManagerTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.manager = User.objects.create_user(
            username="cm", password="pass"
        )
        self.other_manager = User.objects.create_user(
            username="cm2", password="pass"
        )

        self.group = Group.objects.create(name="Collection Managers")
        self.group.user_set.add(self.manager, self.other_manager)

        self.patcher = patch("cms.models.get_current_user", return_value=self.manager)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

        AccessionNumberSeries.objects.create(
            user=self.manager,
            start_from=1,
            end_at=100,
            current_number=1,
            is_active=True,
        )

        self.unassigned = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.manager,
        )
        self.assigned = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
            accessioned_by=self.manager,
        )
        AccessionRow.objects.create(accession=self.assigned)

        for i in range(3, 14):
            Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=i,
                accessioned_by=self.manager,
            )

        self.client.login(username="cm", password="pass")

    def test_collection_manager_dashboard_lists(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["role"], "Collection Manager")
        self.assertTrue(response.context["has_active_series"])
        self.assertIn(self.unassigned, response.context["unassigned_accessions"])
        self.assertNotIn(self.assigned, response.context["unassigned_accessions"])
        self.assertEqual(len(response.context["latest_accessions"]), 10)

    def test_collection_manager_without_active_series(self):
        AccessionNumberSeries.objects.filter(user=self.manager).update(is_active=False)
        response = self.client.get(reverse("dashboard"))
        self.assertFalse(response.context["has_active_series"])

