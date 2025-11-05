import pytest
from django.conf import settings
from pathlib import Path


pytestmark = pytest.mark.django_db


def test_responsive_css_contains_large_screen_constraint():
    """Test that style.css includes responsive layout rules for large screens."""
    css_path = Path(settings.BASE_DIR, "cms", "static", "css", "style.css")
    content = css_path.read_text(encoding="utf-8")
    
    # Check for media query targeting large screens (993px+)
    assert "@media screen and (min-width: 993px)" in content
    
    # Check for max-width constraint
    assert "max-width: 900px" in content
    
    # Check for centering with auto margins
    assert "margin-left: auto" in content
    assert "margin-right: auto" in content
    
    # Check that it targets the main content container
    assert ".site-main .container-fluid" in content


def test_base_template_has_container_structure():
    """Test that base_generic.html has the expected container structure."""
    template_path = Path(settings.BASE_DIR, "cms", "templates", "base_generic.html")
    content = template_path.read_text(encoding="utf-8")
    
    # Check for main content wrapper
    assert '<main id="main-content" class="site-main">' in content
    
    # Check for container-fluid div
    assert '<div class="container-fluid">' in content
