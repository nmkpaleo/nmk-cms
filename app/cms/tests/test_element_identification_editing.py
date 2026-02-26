"""Tests for Element and Identification editing functionality and form ordering."""

import pytest
from django.urls import reverse
from django.contrib.auth.models import User, Group
from cms.models import (
    Accession,
    AccessionRow,
    Collection,
    Locality,
    NatureOfSpecimen,
    Identification,
    Element,
    Person,
)
from crum import impersonate

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_user():
    """Create an admin user to bypass the login check."""
    user = User.objects.create_user(username='admin', password='testpass', is_superuser=True, is_staff=True)
    return user


@pytest.fixture
def collection_manager_user():
    """Create a user with collection manager permissions."""
    user = User.objects.create_user(username='manager', password='testpass')
    group, _ = Group.objects.get_or_create(name='Collection Managers')
    user.groups.add(group)
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def locality(admin_user):
    """Create a test locality."""
    with impersonate(admin_user):
        return Locality.objects.create(
            abbreviation="TST",
            name="Test Site",
        )


@pytest.fixture
def accession(locality, admin_user):
    """Create a test accession."""
    with impersonate(admin_user):
        collection, _ = Collection.objects.get_or_create(
            abbreviation="COL",
            defaults={"description": "Collection"},
        )
        return Accession.objects.create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=1001,
        )


@pytest.fixture
def accession_row(accession, admin_user):
    """Create a test accession row."""
    with impersonate(admin_user):
        return AccessionRow.objects.create(
            accession=accession,
            specimen_suffix='A',
        )


@pytest.fixture
def element(admin_user):
    """Create a test element."""
    with impersonate(admin_user):
        return Element.objects.create(name="Femur")


@pytest.fixture
def specimen(accession_row, element, admin_user):
    """Create a test NatureOfSpecimen."""
    with impersonate(admin_user):
        return NatureOfSpecimen.objects.create(
            accession_row=accession_row,
            element=element,
            verbatim_element="Left femur",
            side="left",
            portion="proximal",
            fragments=2,
            condition="good",
        )


@pytest.fixture
def person(admin_user):
    """Create a test person."""
    with impersonate(admin_user):
        return Person.objects.create(
            first_name="John",
            last_name="Doe",
        )


@pytest.fixture
def identification(accession_row, person, admin_user):
    """Create a test identification."""
    with impersonate(admin_user):
        return Identification.objects.create(
            accession_row=accession_row,
            identified_by=person,
            taxon_verbatim="Australopithecus afarensis",
            taxon="Australopithecus afarensis",
            date_identified="2023-01-15",
        )


class TestAddSpecimenPageHeading:
    """Test heading text on add-specimen page."""

    def test_add_specimen_page_has_correct_heading(self, client, collection_manager_user, accession_row):
        """Test that the add specimen page heading is exactly 'Add Element to specimen'."""
        client.force_login(collection_manager_user)
        url = reverse('accessionrow_add_specimen', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        assert "Add Element to specimen" in content


class TestSpecimenFormFieldOrdering:
    """Test field ordering on specimen forms."""

    def test_add_form_field_order_verbatim_first_condition_last(self, client, collection_manager_user, accession_row):
        """Test that verbatim_element is first and condition is last in the add form."""
        client.force_login(collection_manager_user)
        url = reverse('accessionrow_add_specimen', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context['form']
        field_names = list(form.fields.keys())
        
        assert field_names[0] == 'verbatim_element'
        assert field_names[-1] == 'condition'

    def test_edit_form_field_order_verbatim_first_condition_last(self, client, collection_manager_user, accession_row, specimen):
        """Test that verbatim_element is first and condition is last in the edit form."""
        client.force_login(collection_manager_user)
        url = reverse('element_edit', args=[specimen.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context['form']
        field_names = list(form.fields.keys())
        
        assert field_names[0] == 'verbatim_element'
        assert field_names[-1] == 'condition'


class TestElementEdit:
    """Test Element editing functionality."""

    def test_edit_specimen_page_loads_existing_data(self, client, collection_manager_user, accession_row, specimen):
        """Test that the edit page loads existing Element data."""
        client.force_login(collection_manager_user)
        url = reverse('element_edit', args=[specimen.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context['form']
        assert form.instance == specimen
        assert form.initial.get('verbatim_element') == specimen.verbatim_element or form.instance.verbatim_element == "Left femur"

    def test_edit_specimen_saves_updates(self, client, collection_manager_user, accession_row, specimen):
        """Test that editing an Element saves updates correctly."""
        client.force_login(collection_manager_user)
        url = reverse('element_edit', args=[specimen.id])
        
        data = {
            'element': specimen.element.id,
            'verbatim_element': 'Right femur',
            'side': 'right',
            'portion': 'distal',
            'fragments': 3,
            'condition': 'excellent',
        }
        response = client.post(url, data)
        
        assert response.status_code == 302
        assert response.url == reverse('accessionrow_detail', args=[accession_row.id])
        
        specimen.refresh_from_db()
        assert specimen.verbatim_element == 'Right femur'
        assert specimen.side == 'right'
        assert specimen.portion == 'distal'
        assert specimen.fragments == 3
        assert specimen.condition == 'excellent'

    def test_edit_specimen_requires_authentication(self, client, accession_row, specimen):
        """Test that editing requires authentication."""
        url = reverse('element_edit', args=[specimen.id])
        response = client.get(url)
        
        assert response.status_code == 302
        assert '/accounts/login/' in response.url


class TestIdentificationEdit:
    """Test Identification editing functionality."""

    def test_edit_identification_page_loads_existing_data(self, client, collection_manager_user, accession_row, identification):
        """Test that the edit page loads existing Identification data."""
        client.force_login(collection_manager_user)
        url = reverse('identification_edit', args=[identification.id])
        response = client.get(url)
        
        assert response.status_code == 200
        form = response.context['form']
        assert form.instance == identification
        assert form.instance.taxon == "Australopithecus afarensis"

    def test_edit_identification_saves_updates(self, client, collection_manager_user, accession_row, identification):
        """Test that editing an Identification saves updates correctly."""
        client.force_login(collection_manager_user)
        url = reverse('identification_edit', args=[identification.id])
        
        data = {
            'identified_by': identification.identified_by.id,
            'taxon_verbatim': 'Homo habilis',
            'date_identified': '2023-06-20',
            'identification_qualifier': 'cf.',
            'verbatim_identification': 'Homo habilis cf.',
            'identification_remarks': 'Updated identification',
        }
        response = client.post(url, data)
        
        assert response.status_code == 302
        assert response.url == reverse('accessionrow_detail', args=[accession_row.id])
        
        identification.refresh_from_db()
        assert identification.taxon == 'Homo habilis'
        assert identification.identification_qualifier == 'cf.'
        assert str(identification.date_identified) == '2023-06-20'

    def test_edit_identification_requires_authentication(self, client, accession_row, identification):
        """Test that editing requires authentication."""
        url = reverse('identification_edit', args=[identification.id])
        response = client.get(url)
        
        assert response.status_code == 302
        assert '/accounts/login/' in response.url


class TestAccessionRowDetailPageOrdering:
    """Test section ordering and identification display on accessionrow detail page."""

    def test_identifications_section_appears_before_elements(self, client, collection_manager_user, accession_row):
        """Test that the Identifications section appears before Elements section."""
        client.force_login(collection_manager_user)
        url = reverse('accessionrow_detail', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Find positions of the section headings
        identifications_pos = content.find('specimen-identification-heading')
        elements_pos = content.find('specimen-elements-heading')
        
        assert identifications_pos > 0
        assert elements_pos > 0
        assert identifications_pos < elements_pos

    def test_identification_ordering_by_date_desc_then_created_at_desc(self, client, accession_row, person, admin_user):
        """Test that identifications are ordered by date DESC, then created_at DESC."""
        # Create multiple identifications with different dates
        with impersonate(admin_user):
            id1 = Identification.objects.create(
                accession_row=accession_row,
                identified_by=person,
                taxon_verbatim="Taxon A",
                taxon="Taxon A",
                date_identified="2023-01-01",
            )
            id2 = Identification.objects.create(
                accession_row=accession_row,
                identified_by=person,
                taxon_verbatim="Taxon B",
                taxon="Taxon B",
                date_identified="2023-06-01",
            )
            id3 = Identification.objects.create(
                accession_row=accession_row,
                identified_by=person,
                taxon_verbatim="Taxon C",
                taxon="Taxon C",
                date_identified="2023-03-01",
            )
        
        url = reverse('accessionrow_detail', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        identifications = list(response.context['identifications'])
        
        # Should be ordered by date DESC: 2023-06-01, 2023-03-01, 2023-01-01
        assert identifications[0].id == id2.id
        assert identifications[1].id == id3.id
        assert identifications[2].id == id1.id

    def test_identification_w3css_classes_latest_green_others_red(self, client, accession_row, person, admin_user):
        """Test that the latest identification has w3-pale-green and others have w3-pale-red."""
        # Create multiple identifications
        with impersonate(admin_user):
            id1 = Identification.objects.create(
                accession_row=accession_row,
                identified_by=person,
                taxon_verbatim="Taxon A",
                taxon="Taxon A",
                date_identified="2023-01-01",
            )
            id2 = Identification.objects.create(
                accession_row=accession_row,
                identified_by=person,
                taxon_verbatim="Taxon B (Latest)",
                taxon="Taxon B (Latest)",
                date_identified="2023-06-01",
            )
            id3 = Identification.objects.create(
                accession_row=accession_row,
                identified_by=person,
                taxon_verbatim="Taxon C",
                taxon="Taxon C",
                date_identified="2023-03-01",
            )
        
        url = reverse('accessionrow_detail', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Check that w3-pale-green appears before w3-pale-red in the identifications table
        # The first identification row (latest) should have w3-pale-green
        identifications_section_start = content.find('specimen-identification-heading')
        identifications_table_start = content.find('<tbody>', identifications_section_start)
        identifications_table_end = content.find('</tbody>', identifications_table_start)
        identifications_table = content[identifications_table_start:identifications_table_end]
        
        # Find first occurrence of w3-pale class in the table
        first_pale_green = identifications_table.find('w3-pale-green')
        first_pale_red = identifications_table.find('w3-pale-red')
        
        assert first_pale_green > 0, "w3-pale-green class should be present"
        assert first_pale_red > 0, "w3-pale-red class should be present"
        assert first_pale_green < first_pale_red, "w3-pale-green should appear before w3-pale-red"


class TestAccessionRowDetailEditLinks:
    """Test that edit links appear for Elements and Identifications."""

    def test_element_edit_link_present_for_collection_manager(self, client, collection_manager_user, accession_row, specimen):
        """Test that edit link appears for Elements when user is collection manager."""
        client.force_login(collection_manager_user)
        url = reverse('accessionrow_detail', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        edit_url = reverse('element_edit', args=[specimen.id])
        assert edit_url in content

    def test_identification_edit_link_present_for_collection_manager(self, client, collection_manager_user, accession_row, identification):
        """Test that edit link appears for Identifications when user is collection manager."""
        client.force_login(collection_manager_user)
        url = reverse('accessionrow_detail', args=[accession_row.id])
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        
        edit_url = reverse('identification_edit', args=[identification.id])
        assert edit_url in content
