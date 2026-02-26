from django.test.utils import setup_test_environment, teardown_test_environment
import pytest


@pytest.fixture(scope="session", autouse=True)
def django_test_environment():
    setup_test_environment()
    yield
    teardown_test_environment()

