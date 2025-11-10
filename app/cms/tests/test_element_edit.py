"""Tests for element (NatureOfSpecimen) editing functionality."""

import pytest
from django.urls import reverse
from django.test import Client
from cms.models import (
    Accession,
    AccessionRow,
    Collection,
    Element,
    Locality,
    NatureOfSpecimen,
)
from django.contrib.auth.models import User, Group


pytestmark = pytest.mark.django_db


@pytest.fixture
def collection_manager_user():
    """Create a user with collection manager permissions."""
    user = User.objects.create_user(
        username="manager",
        password="testpass123",
        email="manager@test.com"
    )
    # Create collection manager group if it doesn't exist
    group, _ = Group.objects.get_or_create(name="Collection Manager")
    user.groups.add(group)
    return user


@pytest.fixture
def accession_with_element(collection_manager_user):
    """Create a test accession with an element."""
    # Create required related objects
    collection, _ = Collection.objects.get_or_create(
        abbreviation="TEST",
        defaults={"description": "Test Collection"}
    )
    
    locality, _ = Locality.objects.get_or_create(
        abbreviation="TL",
        defaults={"name": "Test Locality"}
    )
    
    element, _ = Element.objects.get_or_create(
        name="Femur",
        defaults={"parent_element": None}
    )
    
    # Create accession and accession row
    accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=1
    )
    
    accession_row = AccessionRow.objects.create(
        accession=accession,
        specimen_suffix="A"
    )
    
    # Create nature of specimen (element)
    nature_of_specimen = NatureOfSpecimen.objects.create(
        accession_row=accession_row,
        element=element,
        verbatim_element="Left femur",
        side="Left",
        condition="Complete",
        portion="Whole",
        fragments=0
    )
    
    return {
        'accession': accession,
        'accession_row': accession_row,
        'element': nature_of_specimen,
        'element_model': element
    }


def test_element_edit_url_exists(accession_with_element):
    """Test that the element edit URL pattern exists."""
    element = accession_with_element['element']
    url = reverse('element_edit', args=[element.id])
    assert url == f'/elements/{element.id}/edit/'


def test_element_edit_view_requires_login(client, accession_with_element):
    """Test that element edit view requires authentication."""
    element = accession_with_element['element']
    url = reverse('element_edit', args=[element.id])
    response = client.get(url)
    # Should redirect to login
    assert response.status_code == 302
    assert '/login/' in response.url or '/accounts/login/' in response.url


def test_element_edit_view_requires_collection_manager(client, accession_with_element):
    """Test that element edit view requires collection manager permission."""
    # Create a regular user without collection manager permissions
    regular_user = User.objects.create_user(
        username="regular",
        password="testpass123"
    )
    client.login(username="regular", password="testpass123")
    
    element = accession_with_element['element']
    url = reverse('element_edit', args=[element.id])
    response = client.get(url)
    
    # Should be forbidden or redirect
    assert response.status_code in [302, 403]


def test_element_edit_get_shows_form(client, collection_manager_user, accession_with_element):
    """Test that GET request to element edit shows the form with current data."""
    client.login(username="manager", password="testpass123")
    
    element = accession_with_element['element']
    url = reverse('element_edit', args=[element.id])
    response = client.get(url)
    
    assert response.status_code == 200
    assert 'form' in response.context
    assert response.context['element'] == element
    assert response.context['accession_row'] == element.accession_row


def test_element_edit_post_updates_element(client, collection_manager_user, accession_with_element):
    """Test that POST request updates the element."""
    client.login(username="manager", password="testpass123")
    
    element = accession_with_element['element']
    element_model = accession_with_element['element_model']
    url = reverse('element_edit', args=[element.id])
    
    updated_data = {
        'verbatim_element': 'Right femur (updated)',
        'element': element_model.id,
        'side': 'Right',
        'condition': 'Fragmentary',
        'portion': 'Proximal half',
        'fragments': 2
    }
    
    response = client.post(url, updated_data)
    
    # Should redirect to accession row detail
    assert response.status_code == 302
    assert response.url == reverse('accessionrow_detail', args=[element.accession_row.id])
    
    # Verify element was updated
    element.refresh_from_db()
    assert element.verbatim_element == 'Right femur (updated)'
    assert element.side == 'Right'
    assert element.condition == 'Fragmentary'
    assert element.portion == 'Proximal half'
    assert element.fragments == 2


def test_accession_row_detail_shows_edit_buttons(client, collection_manager_user, accession_with_element):
    """Test that accession row detail page shows edit buttons for elements."""
    client.login(username="manager", password="testpass123")
    
    accession_row = accession_with_element['accession_row']
    element = accession_with_element['element']
    
    url = reverse('accessionrow_detail', args=[accession_row.id])
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for edit button
    edit_url = reverse('element_edit', args=[element.id])
    assert edit_url in content
    assert 'Edit' in content


def test_accession_row_specimen_form_field_order():
    """Test that AccessionRowSpecimenForm has correct field order."""
    from cms.forms import AccessionRowSpecimenForm
    
    fields = AccessionRowSpecimenForm.Meta.fields
    
    # Verify verbatim_element is first
    assert fields[0] == 'verbatim_element'
    
    # Verify condition is last
    assert fields[-1] == 'condition'
    
    # Verify all expected fields are present
    expected_fields = ['verbatim_element', 'element', 'side', 'portion', 'fragments', 'condition']
    assert fields == expected_fields
