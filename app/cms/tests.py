from unittest.mock import patch
from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from pathlib import Path

from cms.models import (
    Accession,
    AccessionNumberSeries,
    AccessionRow,
    Collection,
    Locality,
    Place,
    PlaceType,
    PlaceRelation,
    Preparation,
    PreparationStatus,
    UnexpectedSpecimen,
    DrawerRegister,
    Scanning,
    Media,
    Taxon,
)
from cms.utils import generate_accessions_from_series
from cms.forms import DrawerRegisterForm
from cms.filters import DrawerRegisterFilter
from cms.resources import DrawerRegisterResource, PlaceResource
from tablib import Dataset
from cms.upload_processing import process_file
from cms.ocr_processing import process_pending_scans


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
        self.assertEqual(len(response.context["unassigned_accessions"]), 10)
        self.assertNotIn(self.assigned, response.context["unassigned_accessions"])
        self.assertEqual(len(response.context["latest_accessions"]), 10)
        self.assertIn(self.row_accession, response.context["latest_accessions"])

    def test_collection_manager_without_active_series(self):
        AccessionNumberSeries.objects.filter(user=self.manager).update(is_active=False)
        response = self.client.get(reverse("dashboard"))
        self.assertFalse(response.context["has_active_series"])


class DashboardViewPreparatorTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(username="prep", password="pass")

        self.group = Group.objects.create(name="Preparators")
        self.group.user_set.add(self.user)

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

        for i in range(15):
            accession = Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=i,
                accessioned_by=self.user,
            )
            row = AccessionRow.objects.create(accession=accession)
            Preparation.objects.create(
                accession_row=row,
                preparator=self.user,
                preparation_type="cleaning",
                started_on="2023-01-01",
                status=PreparationStatus.IN_PROGRESS,
            )

        self.client.login(username="prep", password="pass")

    def test_preparator_dashboard_lists_limited(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["my_preparations"]), 10)
        self.assertEqual(len(response.context["priority_tasks"]), 10)


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
        self.assertTrue(
            UnexpectedSpecimen.history.filter(identifier="XYZ").exists()
        )


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

    def test_taxa_field_limited_to_orders(self):
        order_taxon = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Ordertaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Ordertaxon",
            family="",
            genus="",
            species="",
        )
        Taxon.objects.create(
            taxon_rank="Family",
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

    def test_edit_form_includes_existing_taxa(self):
        order_taxon = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Ordertaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Ordertaxon",
            family="",
            genus="",
            species="",
        )
        family_taxon = Taxon.objects.create(
            taxon_rank="Family",
            taxon_name="Familytaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="o",
            family="Familytaxon",
            genus="g",
            species="s",
        )
        drawer = DrawerRegister.objects.create(
            code="ABC",
            description="Drawer",
            estimated_documents=1,
        )
        drawer.taxa.add(family_taxon)
        form = DrawerRegisterForm(instance=drawer)
        self.assertEqual(set(form.fields["taxa"].queryset), {order_taxon, family_taxon})

    def test_filter_taxa_field_limited_to_orders(self):
        order_taxon = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Ordertaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Ordertaxon",
            family="",
            genus="",
            species="",
        )
        Taxon.objects.create(
            taxon_rank="Family",
            taxon_name="Familytaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="o",
            family="Familytaxon",
            genus="g",
            species="s",
        )
        f = DrawerRegisterFilter({}, queryset=DrawerRegister.objects.all())
        self.assertEqual(list(f.form.fields["taxa"].queryset), [order_taxon])

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

    def test_order_taxon_str_falls_back_to_name(self):
        taxon = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Coleoptera",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Coleoptera",
            family="",
            genus="",
            species="",
        )
        self.assertEqual(str(taxon), "Coleoptera")

    def test_drawer_register_resource_roundtrip(self):
        loc1 = Locality.objects.create(abbreviation="L1", name="Loc1")
        loc2 = Locality.objects.create(abbreviation="L2", name="Loc2")
        taxon1 = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Order1",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Order1",
            family="",
            genus="",
            species="",
        )
        taxon2 = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Order2",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Order2",
            family="",
            genus="",
            species="",
        )
        user1 = get_user_model().objects.create_user(username="u1")
        user2 = get_user_model().objects.create_user(username="u2")
        drawer = DrawerRegister.objects.create(
            code="ABC",
            description="Desc",
            estimated_documents=5,
            scanning_status=DrawerRegister.ScanningStatus.IN_PROGRESS,
        )
        drawer.localities.set([loc1, loc2])
        drawer.taxa.set([taxon1, taxon2])
        drawer.scanning_users.set([user1, user2])

        resource = DrawerRegisterResource()
        dataset = resource.export()
        DrawerRegister.objects.all().delete()
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        imported = DrawerRegister.objects.get(code="ABC")
        self.assertQuerysetEqual(
            imported.localities.order_by("id"), [loc1, loc2], transform=lambda x: x
        )
        self.assertQuerysetEqual(
            imported.taxa.order_by("id"), [taxon1, taxon2], transform=lambda x: x
        )
        self.assertQuerysetEqual(
            imported.scanning_users.order_by("id"), [user1, user2], transform=lambda x: x
        )

    def test_resource_imports_semicolon_values_with_spaces(self):
        loc1 = Locality.objects.create(abbreviation="L1", name="Loc1")
        loc2 = Locality.objects.create(abbreviation="L2", name="Loc2")
        taxon1 = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Order1",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Order1",
            family="",
            genus="",
            species="",
        )
        taxon2 = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Order2",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Order2",
            family="",
            genus="",
            species="",
        )
        user1 = get_user_model().objects.create_user(username="u1")
        user2 = get_user_model().objects.create_user(username="u2")

        dataset = Dataset(
            headers=[
                "code",
                "description",
                "localities",
                "taxa",
                "estimated_documents",
                "scanning_status",
                "scanning_users",
            ]
        )
        dataset.append(
            [
                "XYZ",
                "Desc",
                f"{loc1.name}; {loc2.name}",
                f"{taxon1.taxon_name}; {taxon2.taxon_name}",
                5,
                DrawerRegister.ScanningStatus.IN_PROGRESS,
                f"{user1.username}; {user2.username}",
            ]
        )

        resource = DrawerRegisterResource()
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        drawer = DrawerRegister.objects.get(code="XYZ")
        self.assertQuerysetEqual(
            drawer.localities.order_by("id"), [loc1, loc2], transform=lambda x: x
        )
        self.assertQuerysetEqual(
            drawer.taxa.order_by("id"), [taxon1, taxon2], transform=lambda x: x
        )
        self.assertQuerysetEqual(
            drawer.scanning_users.order_by("id"), [user1, user2], transform=lambda x: x
        )


class ScanningTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="intern", password="pass")
        group = Group.objects.create(name="Interns")
        self.user.groups.add(group)
        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.drawer = DrawerRegister.objects.create(
            code="ABC", description="Drawer", estimated_documents=1,
            scanning_status=DrawerRegister.ScanningStatus.IN_PROGRESS,
        )
        self.drawer.scanning_users.add(self.user)

    def test_dashboard_lists_drawers_for_intern(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "ABC")
        self.assertContains(response, "Drawer")
        self.assertContains(response, "Start scanning task")
        self.assertContains(response, "Stop scanning task")

    def test_start_and_stop_scan(self):
        self.client.force_login(self.user)
        self.client.post(reverse("drawer_start_scan", args=[self.drawer.id]))
        scan = Scanning.objects.get()
        self.assertIsNotNone(scan.start_time)
        self.assertIsNone(scan.end_time)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, scan.start_time.strftime("%Y-%m-%d"))
        self.assertContains(response, "scan-timer")
        self.client.post(reverse("drawer_stop_scan", args=[self.drawer.id]))
        scan.refresh_from_db()
        self.assertIsNotNone(scan.end_time)

    def test_drawer_detail_shows_scans(self):
        Scanning.objects.create(
            drawer=self.drawer,
            user=self.user,
            start_time=now(),
            end_time=now(),
        )
        admin = get_user_model().objects.create_superuser("admin", "admin@example.com", "pass")
        self.client.force_login(admin)
        response = self.client.get(reverse("drawerregister_detail", args=[self.drawer.id]))
        self.assertContains(response, self.user.username)


class AccessionVisibilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.creator = User.objects.create_user(username="creator", password="pass")
        self.cm_user = User.objects.create_user(username="cm", password="pass")
        self.cm_group = Group.objects.create(name="Collection Managers")
        self.cm_group.user_set.add(self.cm_user)

        self.patcher = patch("cms.models.get_current_user", return_value=self.creator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(abbreviation="COL", description="Test")
        self.locality = Locality.objects.create(abbreviation="LC", name="Loc")

        self.published_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
        )
        self.unpublished_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
        )
        Accession.objects.filter(pk=self.published_accession.pk).update(is_published=True)
        Accession.objects.filter(pk=self.unpublished_accession.pk).update(is_published=False)
        self.published_accession.refresh_from_db()
        self.unpublished_accession.refresh_from_db()

    def test_locality_detail_hides_unpublished_for_public(self):
        url = reverse("locality_detail", args=[self.locality.pk])
        response = self.client.get(url)
        self.assertContains(response, str(self.published_accession.specimen_no))
        self.assertNotIn(
            f"/accessions/{self.unpublished_accession.pk}/",
            response.content.decode(),
        )

    def test_locality_detail_shows_unpublished_for_collection_manager(self):
        self.client.login(username="cm", password="pass")
        url = reverse("locality_detail", args=[self.locality.pk])
        response = self.client.get(url)
        self.assertContains(response, str(self.unpublished_accession.specimen_no))

    def test_accession_detail_unpublished_returns_404_for_public(self):
        url = reverse("accession_detail", args=[self.unpublished_accession.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_accession_detail_unpublished_allowed_for_collection_manager(self):
        self.client.login(username="cm", password="pass")
        url = reverse("accession_detail", args=[self.unpublished_accession.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class PlaceModelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="user", password="pass")
        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

    def test_hierarchy_and_validation(self):
        region = Place.objects.create(
            locality=self.locality,
            name="Region",
            place_type=PlaceType.REGION,
        )
        self.assertEqual(region.part_of_hierarchy, "Region")

        site = Place.objects.create(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=region,
            relation_type=PlaceRelation.PART_OF,
        )
        self.assertEqual(site.part_of_hierarchy, "Region | Site")

        synonym = Place.objects.create(
            locality=self.locality,
            name="R",
            place_type=PlaceType.REGION,
            related_place=region,
            relation_type=PlaceRelation.SYNONYM,
        )
        self.assertEqual(synonym.part_of_hierarchy, region.part_of_hierarchy)

        invalid = Place(
            locality=self.locality,
            name="Invalid",
            place_type=PlaceType.SITE,
            related_place=region,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_related_place_must_share_locality(self):
        other_locality = Locality.objects.create(abbreviation="OT", name="Other")
        region = Place.objects.create(
            locality=other_locality,
            name="OtherRegion",
            place_type=PlaceType.REGION,
        )
        invalid = Place(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=region,
            relation_type=PlaceRelation.PART_OF,
        )
        with self.assertRaisesMessage(ValidationError, "Related place must belong to the same locality."):
            invalid.full_clean()

    def test_prevent_circular_part_of(self):
        parent = Place.objects.create(
            locality=self.locality,
            name="Region",
            place_type=PlaceType.REGION,
        )
        child = Place.objects.create(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=parent,
            relation_type=PlaceRelation.PART_OF,
        )
        parent.related_place = child
        parent.relation_type = PlaceRelation.PART_OF
        with self.assertRaisesMessage(ValidationError, "Cannot set a higher-level place as part of its descendant."):
            parent.full_clean()


class PlaceViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="viewer", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.place = Place.objects.create(
            locality=self.locality,
            name="Region",
            place_type=PlaceType.REGION,
        )

    def test_place_list_view(self):
        response = self.client.get(reverse('place_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Region")

    def test_place_detail_view(self):
        response = self.client.get(reverse('place_detail', args=[self.place.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Higher Geography")
        self.assertContains(response, self.place.part_of_hierarchy)

    def test_place_detail_view_lists_lower_geography(self):
        child = Place.objects.create(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=self.place,
            relation_type=PlaceRelation.PART_OF,
        )
        response = self.client.get(reverse('place_detail', args=[self.place.pk]))
        self.assertContains(response, "Lower Geography")
        self.assertContains(response, child.name)

    def test_place_filter_by_name(self):
        Place.objects.create(locality=self.locality, name="Other", place_type=PlaceType.REGION)
        response = self.client.get(reverse('place_list'), {'name': 'Region'})
        self.assertContains(response, "Region")
        self.assertNotContains(response, "Other")


class PlaceImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="importer", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.resource = PlaceResource()

    def test_invalid_relation_type(self):
        row = {
            'name': 'Test',
            'place_type': PlaceType.REGION,
            'locality': self.locality.abbreviation,
            'relation_type': 'invalid',
        }
        with self.assertRaises(ValueError) as cm:
            self.resource.before_import_row(row, row_number=1)
        self.assertIn('Invalid relation_type', str(cm.exception))

    def test_invalid_place_type(self):
        row = {
            'name': 'Test',
            'place_type': 'InvalidType',
            'locality': self.locality.abbreviation,
        }
        with self.assertRaises(ValueError) as cm:
            self.resource.before_import_row(row, row_number=1)
        self.assertIn('Invalid place_type', str(cm.exception))

    def test_related_place_must_share_locality(self):
        other_locality = Locality.objects.create(abbreviation="OT", name="Other")
        related = Place.objects.create(
            locality=other_locality,
            name="OtherRegion",
            place_type=PlaceType.REGION,
        )
        row = {
            'name': 'Test',
            'place_type': PlaceType.SITE,
            'locality': self.locality.abbreviation,
            'related_place': related.name,
            'relation_type': PlaceRelation.PART_OF,
        }
        with self.assertRaises(ValueError) as cm:
            self.resource.before_import_row(row, row_number=1)
        self.assertIn('must belong to locality', str(cm.exception))

    def test_prevent_circular_part_of(self):
        parent = Place.objects.create(
            locality=self.locality,
            name="Region",
            place_type=PlaceType.REGION,
        )
        child = Place.objects.create(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=parent,
            relation_type=PlaceRelation.PART_OF,
        )
        row = {
            'name': parent.name,
            'place_type': parent.place_type,
            'locality': self.locality.abbreviation,
            'related_place': child.name,
            'relation_type': PlaceRelation.PART_OF,
        }
        with self.assertRaises(ValueError) as cm:
            self.resource.before_import_row(row, row_number=1)
        self.assertIn('higher-level place cannot be part of its descendant', str(cm.exception))


class UploadScanViewTests(TestCase):
    """Tests for the scan upload view and template link."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cm", password="pass", is_staff=True)
        Group.objects.create(name="Collection Managers").user_set.add(self.user)
        self.url = reverse("admin-upload-scan")

    def test_login_required(self):
        response = self.client.get(self.url)
        # Anonymous users should be redirected to the login page
        self.assertEqual(response.status_code, 302)


    def test_admin_index_has_upload_link(self):
        self.client.login(username="cm", password="pass")
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, self.url)

    def test_form_has_multipart_enctype(self):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.url)
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_upload_saves_file(self):
        self.client.login(username="cm", password="pass")
        upload = SimpleUploadedFile("2025-01-01(1).png", b"data", content_type="image/png")
        response = self.client.post(self.url, {"files": upload})
        self.assertEqual(response.status_code, 302)
        pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending" / "2025-01-01(1).png"
        self.assertTrue(pending.exists())
        self.assertTrue(Media.objects.filter(media_location=f"uploads/pending/2025-01-01(1).png").exists())
        pending.unlink()
        import shutil
        shutil.rmtree(pending.parent.parent)

    def test_invalid_names_rejected(self):
        self.client.login(username="cm", password="pass")
        upload = SimpleUploadedFile("badname.png", b"data", content_type="image/png")
        response = self.client.post(self.url, {"files": upload})
        self.assertEqual(response.status_code, 302)
        rejected = Path(settings.MEDIA_ROOT) / "uploads" / "rejected" / "badname.png"
        self.assertTrue(rejected.exists())
        self.assertFalse(Media.objects.filter(media_location="uploads/rejected/badname.png").exists())
        rejected.unlink()
        import shutil
        shutil.rmtree(rejected.parent.parent)


class OcrViewTests(TestCase):
    """Tests for the OCR processing view and link."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cm", password="pass", is_staff=True)
        Group.objects.create(name="Collection Managers").user_set.add(self.user)
        self.url = reverse("admin-do-ocr")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_admin_index_has_ocr_link(self):
        self.client.login(username="cm", password="pass")
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, self.url)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch("cms.ocr_processing.chatgpt_ocr", return_value={"foo": "bar"})
    def test_ocr_moves_file_and_saves_json(self, mock_ocr, mock_detect):
        self.client.login(username="cm", password="pass")
        pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        filename = "2025-01-01(1).png"
        file_path = pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        ocr_file = Path(settings.MEDIA_ROOT) / "uploads" / "ocr" / filename
        self.assertTrue(ocr_file.exists())
        media = Media.objects.get()
        self.assertEqual(media.ocr_status, Media.OCRStatus.COMPLETED)
        self.assertEqual(media.media_location.name, f"uploads/ocr/{filename}")
        self.assertEqual(media.ocr_data["foo"], "bar")
        import shutil
        shutil.rmtree(pending.parent)

    @patch("cms.views.process_pending_scans", return_value=(0, 1, 1, ["test.png: boom"]))
    def test_do_ocr_shows_error_details(self, mock_process):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, "0/1 scans OCR&#x27;d")
        self.assertContains(response, "OCR failed for 1 scans: test.png: boom")

    @patch("cms.views.process_pending_scans", return_value=(3, 0, 5, []))
    def test_do_ocr_reports_progress(self, mock_process):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, "3/5 scans OCR&#x27;d")


class ProcessPendingScansTests(TestCase):
    def setUp(self):
        import shutil

        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
        self.pending.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.pending.parent, ignore_errors=True))

    @patch("cms.ocr_processing.detect_card_type", side_effect=Exception("boom"))
    def test_failure_logs_and_records_error(self, mock_detect):
        filename = "error.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        with self.assertLogs("cms.ocr_processing", level="ERROR") as cm:
            successes, failures, total, errors = process_pending_scans()
        self.assertEqual(successes, 0)
        self.assertEqual(failures, 1)
        self.assertEqual(total, 1)
        self.assertTrue(any("boom" in e for e in errors))
        self.assertTrue(any("boom" in m for m in cm.output))
        media = Media.objects.get()
        self.assertEqual(media.ocr_status, Media.OCRStatus.FAILED)
        self.assertEqual(media.ocr_data["error"], "boom")
        self.assertEqual(media.media_location.name, f"uploads/failed/{filename}")
        failed_file = Path(settings.MEDIA_ROOT) / "uploads" / "failed" / filename
        self.assertTrue(failed_file.exists())


class UploadProcessingTests(TestCase):
    """Tests for the file watcher processing logic."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="intern", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.drawer = DrawerRegister.objects.create(
            code="DRW", description="Drawer", estimated_documents=1
        )
        start = now() - timedelta(minutes=5)
        end = now() + timedelta(minutes=5)
        self.scanning = Scanning.objects.create(
            drawer=self.drawer, user=self.user, start_time=start, end_time=end
        )

    def test_scanning_lookup_uses_creation_time(self):
        incoming = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        filename = "2025-09-09(1).png"
        src = incoming / filename
        src.write_bytes(b"data")
        created = self.scanning.start_time + timedelta(minutes=1)
        stat_result = SimpleNamespace(st_ctime=created.timestamp(), st_mode=0)
        with patch("pathlib.Path.stat", return_value=stat_result):
            process_file(src)
        media = Media.objects.get(media_location=f"uploads/pending/{filename}")
        self.assertEqual(media.scanning, self.scanning)
        import shutil
        shutil.rmtree(incoming.parent)


class MediaFileDeletionTests(TestCase):
    """Ensure deleting a Media record removes its file from disk."""

    def setUp(self):
        import shutil

        User = get_user_model()
        self.user = User.objects.create_user(username="deleter", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.uploads = Path(settings.MEDIA_ROOT) / "uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.uploads, ignore_errors=True))

    def test_file_removed_on_delete(self):
        file_path = self.uploads / "deleteme.png"
        file_path.write_bytes(b"data")
        media = Media.objects.create(media_location="uploads/deleteme.png")
        self.assertTrue(file_path.exists())
        media.delete()
        self.assertFalse(file_path.exists())


class AdminAutocompleteTests(TestCase):
    """Ensure admin uses select2 autocomplete for heavy foreign keys."""

    def test_media_admin_autocomplete_fields(self):
        from django.contrib.admin.sites import site

        media_admin = site._registry[Media]
        self.assertEqual(
            list(media_admin.autocomplete_fields),
            ["accession", "accession_row", "scanning"],
        )

    def test_scanning_admin_search_fields(self):
        from django.contrib.admin.sites import site

        scanning_admin = site._registry[Scanning]
        self.assertIn("drawer__code", scanning_admin.search_fields)
        self.assertIn("user__username", scanning_admin.search_fields)
