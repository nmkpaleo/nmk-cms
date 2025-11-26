from crum import get_current_user, set_current_user
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from cms.filters import (
    AccessionFilter,
    DrawerRegisterFilter,
    FieldSlipFilter,
    LocalityFilter,
    PlaceFilter,
    PreparationFilter,
    ReferenceFilter,
    StorageFilter,
)
from cms.models import (
    Accession,
    AccessionRow,
    Collection,
    DrawerRegister,
    Identification,
    Locality,
    Organisation,
    Taxon,
    TaxonExternalSource,
    TaxonRank,
    TaxonStatus,
    UserOrganisation,
)
from cms.views import AccessionListView


def _extract_class_tokens(widget) -> list[str]:
    """Return all CSS class tokens applied to a widget or its subwidgets."""

    def _split_classes(class_value: str | None) -> list[str]:
        if not class_value:
            return []
        return [token for token in class_value.split() if token]

    if hasattr(widget, "widgets"):
        tokens: list[str] = []
        for subwidget in widget.widgets:
            tokens.extend(_split_classes(subwidget.attrs.get("class")))
        return tokens
    return _split_classes(widget.attrs.get("class"))


def make_taxon(
    name: str,
    *,
    status: str = TaxonStatus.ACCEPTED,
    rank: str = TaxonRank.SPECIES,
    family: str = "Familia",
    is_active: bool = True,
    external_id: str | None = None,
    accepted_taxon: Taxon | None = None,
    scientific_name_authorship: str = "Author",
) -> Taxon:
    previous_user = get_current_user()
    user_model = get_user_model()
    creator, _ = user_model.objects.get_or_create(
        username="taxon-maker", defaults={"is_superuser": True, "is_staff": True}
    )
    set_current_user(creator)

    parts = name.split()
    genus = parts[0]
    species = parts[1] if len(parts) > 1 else parts[0]
    try:
        return Taxon.objects.create(
            external_source=TaxonExternalSource.NOW,
            external_id=external_id,
            author_year="Author 1900",
            status=status,
            accepted_taxon=accepted_taxon if status == TaxonStatus.SYNONYM else None,
            parent=None,
            is_active=is_active,
            source_version="v1",
            taxon_rank=rank,
            taxon_name=name,
            kingdom="Animalia",
            phylum="Chordata",
            class_name="Mammalia",
            order="Orderus",
            superfamily="",
            family=family,
            subfamily="",
            tribe="",
            genus=genus,
            species=species,
            infraspecific_epithet="",
            scientific_name_authorship=scientific_name_authorship,
        )
    finally:
        set_current_user(previous_user)


def make_accession(*, accessioned_by=None, created_by=None) -> Accession:
    previous_user = get_current_user()
    user_model = get_user_model()
    creator = created_by or accessioned_by
    if creator is None:
        creator, _ = user_model.objects.get_or_create(
            username="collection-maker", defaults={"is_superuser": True, "is_staff": True}
        )

    set_current_user(creator)
    try:
        collection = Collection.objects.create(abbreviation="COL", description="Collection")
        locality = Locality.objects.create(abbreviation="LC", name="Locality")
        accession = Accession.objects.create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=1,
        )
        if accessioned_by:
            accession.accessioned_by = accessioned_by
            accession.save(update_fields=["accessioned_by"])
        return accession
    finally:
        set_current_user(previous_user)


class AccessionFilterTests(TestCase):
    databases = {"default"}

    def test_accession_filter_matches_taxon_record_name(self):
        accession = make_accession()
        accession_row = AccessionRow.objects.create(accession=accession)
        accepted = make_taxon(
            "Ferrequitherium sweeti", external_id="NOW:species:Ferrequitherium sweeti"
        )
        Identification.objects.create(
            accession_row=accession_row,
            taxon_verbatim=accepted.taxon_name,
        )
        synonym = make_taxon(
            "Ferrequitherium junior",
            status=TaxonStatus.SYNONYM,
            accepted_taxon=accepted,
            external_id="NOW:syn:Ferrequitherium junior::accepted:Ferrequitherium sweeti",
        )

        qs = Accession.objects.all()
        filterset = AccessionFilter(data={"taxon": synonym.taxon_name}, queryset=qs)

        self.assertIn(accession, filterset.qs)

    def test_accession_filter_matches_verbatim_taxon_name_without_record(self):
        accession = make_accession()
        accession_row = AccessionRow.objects.create(accession=accession)
        Identification.objects.create(
            accession_row=accession_row,
            taxon_verbatim="Unmatchedus example",
        )

        qs = Accession.objects.all()
        filterset = AccessionFilter(data={"taxon": "Unmatched"}, queryset=qs)

        self.assertIn(accession, filterset.qs)

    def test_accession_filter_family_uses_taxon_record_attribute(self):
        accession = make_accession()
        accession_row = AccessionRow.objects.create(accession=accession)
        accepted = make_taxon(
            "Familitaxon example",
            external_id="NOW:species:Familitaxon example",
            family="Testidae",
        )
        Identification.objects.create(
            accession_row=accession_row,
            taxon_verbatim=accepted.taxon_name,
        )

        qs = Accession.objects.all()
        filterset = AccessionFilter(data={"family": "Testid"}, queryset=qs)

        self.assertIn(accession, filterset.qs)

    def test_accession_filter_species_matches_verbatim_without_link(self):
        user_model = get_user_model()
        user = user_model.objects.create(username="filter-user")
        previous_user = get_current_user()
        set_current_user(user)

        accession = make_accession()
        accession_row = AccessionRow.objects.create(accession=accession)
        make_taxon(
            "Filtertaxon example",
            external_id="NOW:species:Filtertaxon example",
            scientific_name_authorship="Author One",
        )
        make_taxon(
            "Filtertaxon example",
            external_id="NOW:species:Filtertaxon example:dup",
            scientific_name_authorship="Author Two",
        )

        Identification.objects.create(
            accession_row=accession_row,
            taxon_verbatim="Filtertaxon example",
        )

        set_current_user(previous_user)

        qs = Accession.objects.all()
        filterset = AccessionFilter(data={"species": "example"}, queryset=qs)

        self.assertIn(accession, filterset.qs)

    def test_filter_widgets_expose_w3_classes(self):
        filter_classes = [
            AccessionFilter,
            PreparationFilter,
            LocalityFilter,
            PlaceFilter,
            ReferenceFilter,
            FieldSlipFilter,
            DrawerRegisterFilter,
            StorageFilter,
        ]

        for filter_cls in filter_classes:
            with self.subTest(filter=filter_cls.__name__):
                model = filter_cls.Meta.model
                filterset = filter_cls(data={}, queryset=model.objects.none())
                for field in filterset.form.fields.values():
                    tokens = _extract_class_tokens(field.widget)
                    self.assertTrue(
                        any(token.startswith("w3-") for token in tokens),
                        msg=(
                            f"Expected at least one W3.CSS class on field '{field.label}'"
                        ),
                    )

    def test_accession_filter_limits_organisations_for_non_superusers(self):
        organisation, _ = Organisation.objects.get_or_create(name="NMK", code="nmk")
        Organisation.objects.get_or_create(name="TBI", code="tbi")
        user_model = get_user_model()
        user = user_model.objects.create_user(username="org-user")
        UserOrganisation.objects.create(user=user, organisation=organisation)

        request = RequestFactory().get("/accessions/")
        request.user = user

        filterset = AccessionFilter(
            data={}, queryset=Accession.objects.none(), request=request
        )

        organisation_field = filterset.form.fields["organisation"]
        self.assertEqual(list(organisation_field.queryset), [organisation])

    def test_accession_filter_by_organisation_matches_accessioned_user(self):
        organisation, _ = Organisation.objects.get_or_create(name="NMK", code="nmk")
        other_org, _ = Organisation.objects.get_or_create(name="TBI", code="tbi")
        user_model = get_user_model()
        nmk_user = user_model.objects.create_user(username="nmk-user")
        tbi_user = user_model.objects.create_user(username="tbi-user")
        UserOrganisation.objects.create(user=nmk_user, organisation=organisation)
        UserOrganisation.objects.create(user=tbi_user, organisation=other_org)

        nmk_accession = make_accession(accessioned_by=nmk_user)
        make_accession(accessioned_by=tbi_user)

        filterset = AccessionFilter(
            data={"organisation": organisation.pk}, queryset=Accession.objects.all()
        )

        self.assertEqual(list(filterset.qs), [nmk_accession])

    def test_accession_list_view_paginates_with_organisation_filter(self):
        organisation, _ = Organisation.objects.get_or_create(name="NMK", code="nmk")
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="nmk-user", is_superuser=True, is_staff=True
        )
        UserOrganisation.objects.create(user=user, organisation=organisation)

        for index in range(12):
            accession = make_accession(accessioned_by=user)
            accession.specimen_no = index + 1
            accession.save(update_fields=["specimen_no"])

        factory = RequestFactory()
        request = factory.get(
            "/accessions/", {"organisation": organisation.pk, "page": 2}
        )
        request.user = user

        response = AccessionListView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        page_obj = response.context_data["page_obj"]
        self.assertEqual(page_obj.paginator.count, 12)
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(len(page_obj.object_list), 2)
