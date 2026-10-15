import pytest
from django.conf import settings
from pathlib import Path


pytestmark = pytest.mark.django_db


def test_responsive_css_contains_large_screen_constraint():
    """Test that style.css includes responsive layout rules for shared containers."""
    css_path = Path(settings.BASE_DIR, "cms", "static", "css", "style.css")
    content = css_path.read_text(encoding="utf-8")

    # Check for responsive max-width constraints on the shared content container.
    assert ".site-main > .container-fluid" in content
    assert "width: min(100% - 32px, 1440px)" in content
    assert "width: min(100% - 20px, 1440px)" in content

    # Check for centering with auto margins.
    assert "margin-left: auto" in content
    assert "margin-right: auto" in content


def test_base_template_has_container_structure():
    """Test that base_generic.html has the expected container structure."""
    template_path = Path(settings.BASE_DIR, "cms", "templates", "base_generic.html")
    content = template_path.read_text(encoding="utf-8")
    
    # Check for main content wrapper
    assert '<main id="main-content" class="site-main">' in content
    
    # Check for container-fluid div
    assert '<div class="container-fluid">' in content
