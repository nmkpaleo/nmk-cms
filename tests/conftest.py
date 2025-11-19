import pytest
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment, teardown_test_environment


@pytest.fixture(scope="session", autouse=True)
def django_test_environment():
    setup_test_environment()
    yield
    teardown_test_environment()


@pytest.fixture(scope="session")
def django_db_setup():
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    yield
    runner.teardown_databases(old_config)


@pytest.fixture()
def db(django_db_setup):
    """Compatibility fixture matching pytest-django's signature."""
    pass
