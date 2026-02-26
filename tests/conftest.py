from django.test.utils import _TestState, setup_test_environment, teardown_test_environment
import pytest


@pytest.fixture(scope="session", autouse=True)
def django_test_environment():
    already_configured = hasattr(_TestState, "saved_data")
    if not already_configured:
        setup_test_environment()
    try:
        yield
    finally:
        if not already_configured and hasattr(_TestState, "saved_data"):
            teardown_test_environment()

