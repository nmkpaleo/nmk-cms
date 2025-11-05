import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from app.cms.models import Locality

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    user_model = get_user_model()
    return user_model.objects.create(username="geologist")


@pytest.fixture(autouse=True)
def cleanup_current_user():
    try:
        yield
    finally:
        set_current_user(None)


def test_locality_defaults_to_empty_geological_times(user):
    set_current_user(user)
    locality = Locality.objects.create(abbreviation="KM", name="Koobi Fora")

    assert locality.geological_times == []


def test_locality_clean_rejects_invalid_geological_times(user):
    locality = Locality(
        abbreviation="NB",
        name="Nairobi Basin",
        geological_times=["Invalid"],
    )

    set_current_user(user)
    with pytest.raises(ValidationError) as exc:
        locality.full_clean()

    assert "geological_times" in exc.value.message_dict


def test_locality_history_tracks_geological_times(user):
    set_current_user(user)
    locality = Locality.objects.create(abbreviation="TS", name="Turkana Site")

    locality.geological_times = [Locality.GeologicalTime.MIOCENE]
    locality.save()

    history = locality.history.latest()
    assert history.geological_times == [Locality.GeologicalTime.MIOCENE]
