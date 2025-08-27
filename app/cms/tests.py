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
    UnexpectedSpecimen,
    DrawerRegister,
    DrawerRegisterLog,
    Taxon,
)
from cms.utils import generate_accessions_from_series
from cms.forms import DrawerRegisterForm
from cms.filters import DrawerRegisterFilter


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

        with patch("cms.models.get_current_user", return_value=self.other_manager):
            self.row_accession = Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=99,
                accessioned_by=self.other_manager,
            )

        AccessionRow.objects.create(accession=self.row_accession)

        self.client.login(username="cm", password="pass")

    def test_collection_manager_dashboard_lists(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_collection_manager"])
        self.assertTrue(response.context["has_active_series"])
        self.assertIn(self.unassigned, response.context["unassigned_accessions"])
        self.assertNotIn(self.assigned, response.context["unassigned_accessions"])
        self.assertEqual(len(response.context["latest_accessions"]), 10)
        self.assertIn(self.row_accession, response.context["latest_accessions"])

    def test_collection_manager_without_active_series(self):
        AccessionNumberSeries.objects.filter(user=self.manager).update(is_active=False)
        response = self.client.get(reverse("dashboard"))
        self.assertFalse(response.context["has_active_series"])


class DashboardViewMultipleRolesTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(username="multi", password="pass")

        self.prep_group = Group.objects.create(name="Preparators")
        self.cm_group = Group.objects.create(name="Collection Managers")
        self.prep_group.user_set.add(self.user)
        self.cm_group.user_set.add(self.user)

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

        AccessionNumberSeries.objects.create(
            user=self.user,
            start_from=1,
            end_at=100,
            current_number=1,
            is_active=True,
        )

        self.unassigned = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.user,
        )

        self.prep_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
            accessioned_by=self.user,
        )
        self.accession_row = AccessionRow.objects.create(accession=self.prep_accession)
        self.preparation = Preparation.objects.create(
            accession_row=self.accession_row,
            preparator=self.user,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.IN_PROGRESS,
        )

        self.client.login(username="multi", password="pass")

    def test_dashboard_shows_all_role_sections(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_preparator"])
        self.assertTrue(response.context["is_collection_manager"])
        self.assertIn(self.preparation, response.context["my_preparations"])
        self.assertIn(self.unassigned, response.context["unassigned_accessions"])


class UnexpectedSpecimenLoggingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_logging_creates_record(self):
        self.client.login(username="tester", password="pass")
        response = self.client.post(reverse("inventory_log_unexpected"), {"identifier": "XYZ"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UnexpectedSpecimen.objects.filter(identifier="XYZ").exists())


class DrawerRegisterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cm", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_requires_user_when_in_progress(self):
        form = DrawerRegisterForm(
            data={
                "code": "ABC",
                "description": "Test",
                "estimated_documents": 5,
                "scanning_status": DrawerRegister.ScanningStatus.IN_PROGRESS,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Scanning user is required", form.non_field_errors()[0])

    def test_logging_on_status_and_user_change(self):
        drawer = DrawerRegister.objects.create(
            code="DEF", description="Drawer", estimated_documents=10
        )
        other = get_user_model().objects.create_user("other", password="pass")
        form = DrawerRegisterForm(
            data={
                "code": "DEF",
                "description": "Drawer",
                "estimated_documents": 10,
                "scanning_status": DrawerRegister.ScanningStatus.IN_PROGRESS,
                "scanning_users": [other.pk],
                "localities": [],
                "taxa": [],
            },
            instance=drawer,
        )
        self.assertTrue(form.is_valid())
        form.save()
        logs = DrawerRegisterLog.objects.filter(drawer=drawer)
        self.assertEqual(logs.count(), 2)
        self.assertTrue(logs.filter(change_type=DrawerRegisterLog.ChangeType.STATUS).exists())
        self.assertTrue(logs.filter(change_type=DrawerRegisterLog.ChangeType.USER).exists())

    def test_taxa_field_limited_to_orders(self):
        order_taxon = Taxon.objects.create(
            taxon_rank="order",
            taxon_name="Ordertaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Ordertaxon",
            family="f",
            genus="g",
            species="s",
        )
        Taxon.objects.create(
            taxon_rank="family",
            taxon_name="Familytaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="o",
            family="Familytaxon",
            genus="g",
            species="s",
        )
        form = DrawerRegisterForm()
        self.assertEqual(list(form.fields["taxa"].queryset), [order_taxon])

    def test_filter_by_code_and_status(self):
        DrawerRegister.objects.create(
            code="ABC", description="Drawer A", estimated_documents=1
        )
        DrawerRegister.objects.create(
            code="XYZ",
            description="Drawer B",
            estimated_documents=2,
            scanning_status=DrawerRegister.ScanningStatus.SCANNED,
        )

        f = DrawerRegisterFilter({"code": "ABC"}, queryset=DrawerRegister.objects.all())
        self.assertEqual(list(f.qs.values_list("code", flat=True)), ["ABC"])
        f = DrawerRegisterFilter({"scanning_status": DrawerRegister.ScanningStatus.SCANNED}, queryset=DrawerRegister.objects.all())
        self.assertEqual(list(f.qs.values_list("code", flat=True)), ["XYZ"])

