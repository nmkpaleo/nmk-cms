from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext as _


class NavigationTemplateTests(TestCase):
    def test_navigation_structure_anonymous(self):
        response = self.client.get(reverse("index"))

        self.assertContains(response, _("Primary navigation"))
        self.assertContains(response, 'class="w3-bar w3-white w3-card main-navbar"', html=False)
        self.assertContains(response, 'id="primary-navigation"', html=False)
        self.assertContains(response, 'id="reports-menu"', html=False)
        self.assertContains(response, 'class="w3-button nav-link dropdown-toggle"', html=False)
        self.assertContains(response, 'aria-controls="reports-menu"', html=False)
        self.assertContains(response, 'aria-expanded="false"', html=False)
        self.assertContains(response, _("Reports"))
        self.assertContains(response, _("Login"))
        self.assertNotContains(response, _("Logout"))

    def test_navigation_structure_authenticated(self):
        user = get_user_model().objects.create_user(
            username="navtester", email="nav@example.com", password="password123"
        )
        self.client.force_login(user)

        response = self.client.get(reverse("index"))

        self.assertNotContains(response, _("Login"))
        self.assertContains(response, _("Logout"))
        expected_user_label = _("User: %(username)s") % {"username": user.get_username()}
        self.assertContains(response, expected_user_label)
        self.assertContains(response, 'class="nav-item nav-auth"', html=False)
        self.assertContains(response, 'class="w3-button nav-button"', html=False)
        self.assertContains(response, 'form id="logout-form"', html=False)
