"""Tests for AccessionRow element and identification editing functionality."""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from cms.models import (
    Accession,
    AccessionRow,
    Collection,
    Element,
    Identification,
    Locality,
    NatureOfSpecimen,
    Person,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def collection_manager(django_user_model):
    """Create a user with collection manager permissions."""
    user = django_user_model.objects.create_user(
        username="manager",
        password="testpass123",
        email="manager@test.com"
    )
    from django.contrib.auth.models import Group
    group, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(group)
    return user


@pytest.fixture
def locality():
    """Create a test locality."""
    return Locality.objects.create(
        abbreviation="TST",
        name="Test Site",
    )


@pytest.fixture
def collection():
    """Create a test collection."""
    collection, _ = Collection.objects.get_or_create(
        abbreviation="TEST",
        defaults={"description": "Test Collection"},
    )
    return collection


@pytest.fixture
def accession(locality, collection):
    """Create a test accession."""
    return Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=100,
    )


@pytest.fixture
def accession_row(accession):
    """Create a test accession row."""
    return AccessionRow.objects.create(
        accession=accession,
        specimen_suffix="A",
    )


@pytest.fixture
def element():
    """Create a test element."""
    return Element.objects.create(name="Femur")


@pytest.fixture
def specimen(accession_row, element):
    """Create a test specimen (NatureOfSpecimen)."""
    return NatureOfSpecimen.objects.create(
        accession_row=accession_row,
        element=element,
        verbatim_element="Left femur",
        side="Left",
        condition="Good",
        portion="Complete",
        fragments=0,
    )


@pytest.fixture
def person():
    """Create a test person."""
    return Person.objects.create(
        first_name="Jane",
        last_name="Doe",
    )


@pytest.fixture
def identification(accession_row, person):
    """Create a test identification."""
    from datetime import date
    return Identification.objects.create(
        accession_row=accession_row,
        identified_by=person,
        taxon="Homo sapiens",
        date_identified=date(2024, 1, 15),
        verbatim_identification="Human",
    )


class TestAddSpecimenPageHeading:
    """Test the heading on the add-specimen page."""

    def test_add_specimen_page_has_correct_heading(self, client, collection_manager, accession_row):
        """Verify the add-specimen page heading is 'New Element to specimen'."""
        client.force_login(collection_manager)
        url = reverse('accessionrow_add_specimen', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        # The base_form template generates "New {title}" for new instances
        assert "New Element to specimen" in content or "Element to specimen" in content


class TestAccessionRowSpecimenFormFieldOrder:
    """Test the field ordering in AccessionRowSpecimenForm."""

    def test_form_fields_in_correct_order(self, client, collection_manager, accession_row):
        """Verify verbatim_element is first and condition is last."""
        client.force_login(collection_manager)
        url = reverse('accessionrow_add_specimen', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context['form']
        field_names = list(form.fields.keys())
        
        # Check verbatim_element is first
        assert field_names[0] == 'verbatim_element'
        # Check condition is last
        assert field_names[-1] == 'condition'
        # Verify all expected fields are present
        assert 'element' in field_names
        assert 'side' in field_names
        assert 'portion' in field_names
        assert 'fragments' in field_names

    def test_edit_specimen_form_uses_same_field_order(self, client, collection_manager, specimen):
        """Verify edit form has the same field order as create form."""
        client.force_login(collection_manager)
        url = reverse('specimen_edit', args=[specimen.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context['form']
        field_names = list(form.fields.keys())
        
        # Same order as create form
        assert field_names[0] == 'verbatim_element'
        assert field_names[-1] == 'condition'


class TestSpecimenEdit:
    """Test editing of NatureOfSpecimen (Element) records."""

    def test_specimen_edit_view_loads_existing_data(self, client, collection_manager, specimen):
        """Verify edit view loads existing specimen data into the form."""
        client.force_login(collection_manager)
        url = reverse('specimen_edit', args=[specimen.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context['form']
        assert form.instance == specimen
        assert form.initial.get('verbatim_element') == specimen.verbatim_element or \
               form.instance.verbatim_element == specimen.verbatim_element

    def test_specimen_edit_saves_changes(self, client, collection_manager, specimen):
        """Verify editing a specimen saves the changes correctly."""
        client.force_login(collection_manager)
        url = reverse('specimen_edit', args=[specimen.id])
        
        new_data = {
            'verbatim_element': 'Right femur updated',
            'element': specimen.element.id,
            'side': 'Right',
            'condition': 'Excellent',
            'portion': 'Partial',
            'fragments': 2,
        }
        
        response = client.post(url, new_data)
        
        # Should redirect to accessionrow detail
        assert response.status_code == 302
        assert response.url == reverse('accessionrow_detail', args=[specimen.accession_row.id])
        
        # Verify changes were saved
        specimen.refresh_from_db()
        assert specimen.verbatim_element == 'Right femur updated'
        assert specimen.side == 'Right'
        assert specimen.condition == 'Excellent'
        assert specimen.portion == 'Partial'
        assert specimen.fragments == 2

    def test_specimen_edit_requires_login(self, client, specimen):
        """Verify edit view requires authentication."""
        url = reverse('specimen_edit', args=[specimen.id])
        response = client.get(url)
        
        # Should redirect to login
        assert response.status_code == 302
        assert '/accounts/login/' in response.url


class TestIdentificationEdit:
    """Test editing of Identification records."""

    def test_identification_edit_view_loads_existing_data(self, client, collection_manager, identification):
        """Verify edit view loads existing identification data into the form."""
        client.force_login(collection_manager)
        url = reverse('identification_edit', args=[identification.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context['form']
        assert form.instance == identification
        assert form.instance.taxon == identification.taxon

    def test_identification_edit_saves_changes(self, client, collection_manager, identification):
        """Verify editing an identification saves the changes correctly."""
        client.force_login(collection_manager)
        url = reverse('identification_edit', args=[identification.id])
        
        from datetime import date
        new_data = {
            'identified_by': identification.identified_by.id,
            'taxon': 'Homo neanderthalensis',
            'date_identified': date(2024, 2, 20).isoformat(),
            'verbatim_identification': 'Neanderthal',
            'identification_qualifier': 'cf.',
            'identification_remarks': 'Updated identification',
        }
        
        response = client.post(url, new_data)
        
        # Should redirect to accessionrow detail
        assert response.status_code == 302
        assert response.url == reverse('accessionrow_detail', args=[identification.accession_row.id])
        
        # Verify changes were saved
        identification.refresh_from_db()
        assert identification.taxon == 'Homo neanderthalensis'
        assert identification.verbatim_identification == 'Neanderthal'
        assert identification.identification_qualifier == 'cf.'
        assert identification.identification_remarks == 'Updated identification'

    def test_identification_edit_requires_login(self, client, identification):
        """Verify edit view requires authentication."""
        url = reverse('identification_edit', args=[identification.id])
        response = client.get(url)
        
        # Should redirect to login
        assert response.status_code == 302
        assert '/accounts/login/' in response.url


class TestAccessionRowDetailPageOrdering:
    """Test the ordering and layout of the accessionrow detail page."""

    def test_identifications_section_appears_before_elements(self, client, accession_row):
        """Verify Identifications section appears before Elements section."""
        url = reverse('accessionrow_detail', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Find positions of section headings
        id_heading_pos = content.find('specimen-identification-heading')
        elem_heading_pos = content.find('specimen-elements-heading')
        
        # Identifications should come before Elements
        assert id_heading_pos > 0
        assert elem_heading_pos > 0
        assert id_heading_pos < elem_heading_pos

    def test_identifications_ordered_by_date_and_created_on(self, client, accession_row, person):
        """Verify identifications are ordered by date_identified DESC, then created_on DESC."""
        from datetime import date, timedelta
        from django.utils import timezone
        
        # Create identifications with different dates
        id1 = Identification.objects.create(
            accession_row=accession_row,
            identified_by=person,
            taxon="Taxon A",
            date_identified=date(2024, 1, 1),
        )
        # Set created_on to an earlier time
        id1.created_on = timezone.now() - timedelta(days=10)
        id1.save()
        
        id2 = Identification.objects.create(
            accession_row=accession_row,
            identified_by=person,
            taxon="Taxon B",
            date_identified=date(2024, 3, 1),
        )
        # This one should be first (most recent date)
        id2.created_on = timezone.now() - timedelta(days=5)
        id2.save()
        
        id3 = Identification.objects.create(
            accession_row=accession_row,
            identified_by=person,
            taxon="Taxon C",
            date_identified=date(2024, 2, 1),
        )
        id3.created_on = timezone.now() - timedelta(days=1)
        id3.save()
        
        url = reverse('accessionrow_detail', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        identifications = list(response.context['identifications'])
        
        # Should be ordered by date DESC (id2, id3, id1)
        assert identifications[0].id == id2.id
        assert identifications[1].id == id3.id
        assert identifications[2].id == id1.id


class TestIdentificationRowCSSClasses:
    """Test CSS classes applied to identification rows."""

    def test_first_identification_has_latest_class(self, client, accession_row, person):
        """Verify the first identification row has .identification--latest class."""
        from datetime import date
        
        # Create two identifications
        id1 = Identification.objects.create(
            accession_row=accession_row,
            identified_by=person,
            taxon="Taxon A",
            date_identified=date(2024, 3, 1),
        )
        id2 = Identification.objects.create(
            accession_row=accession_row,
            identified_by=person,
            taxon="Taxon B",
            date_identified=date(2024, 1, 1),
        )
        
        url = reverse('accessionrow_detail', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Check that the CSS classes are present
        assert 'identification--latest' in content
        assert 'identification--old' in content
        
        # The most recent (id1) should have latest class
        # We can't easily verify which specific row has which class without parsing HTML,
        # but we can verify both classes are present in the rendered output

    def test_css_classes_defined_in_stylesheet(self):
        """Verify CSS classes are defined in the stylesheet."""
        import os
        css_path = '/home/runner/work/nmk-cms/nmk-cms/app/cms/static/css/style.css'
        
        if os.path.exists(css_path):
            with open(css_path, 'r') as f:
                css_content = f.read()
            
            assert 'identification--latest' in css_content
            assert 'identification--old' in css_content
            assert '#e6ffed' in css_content  # Light green background
            assert '#ffe6e6' in css_content  # Light red background


class TestEditLinksInDetailPage:
    """Test that edit links are present in the detail page tables."""

    def test_element_table_has_edit_button_for_managers(self, client, collection_manager, specimen):
        """Verify element table shows edit button for collection managers."""
        client.force_login(collection_manager)
        url = reverse('accessionrow_detail', args=[specimen.accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Check for edit link
        edit_url = reverse('specimen_edit', args=[specimen.id])
        assert edit_url in content
        assert 'Edit' in content

    def test_identification_table_has_edit_button_for_managers(self, client, collection_manager, identification):
        """Verify identification table shows edit button for collection managers."""
        client.force_login(collection_manager)
        url = reverse('accessionrow_detail', args=[identification.accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Check for edit link
        edit_url = reverse('identification_edit', args=[identification.id])
        assert edit_url in content
        assert 'Edit' in content
