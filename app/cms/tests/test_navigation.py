from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext as _


class NavigationTemplateTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user_model = get_user_model()
        self.collection_manager_group = Group.objects.create(name="Collection Managers")

    def _create_user(self, username: str, *, is_superuser: bool = False, groups: list[Group] | None = None):
        email = f"{username}@example.com"
        if is_superuser:
            user = self.user_model.objects.create_superuser(username=username, email=email, password="password123")
        else:
            user = self.user_model.objects.create_user(username=username, email=email, password="password123")

        if groups:
            user.groups.set(groups)
        return user

    def test_navigation_structure_anonymous(self):
        response = self.client.get(reverse("index"))

        self.assertContains(response, _("Primary navigation"))
        self.assertContains(response, 'class="site-navigation w3-bar w3-white w3-card"', html=False)
        self.assertContains(response, 'class="nav-items w3-hide-small"', html=False)
        self.assertContains(response, 'id="primary-navigation"', html=False)
        self.assertContains(response, 'w3-bar-block', html=False)
        self.assertContains(response, 'w3-white', html=False)
        self.assertContains(response, 'w3-hide', html=False)
        self.assertContains(response, 'w3-hide-large', html=False)
        self.assertContains(response, 'w3-hide-medium', html=False)
        self.assertContains(response, _("Login"))
        self.assertNotContains(response, _("Logout"))
        self.assertNotContains(response, 'data-dropdown-toggle="reports-menu"', html=False)
        self.assertContains(response, 'nav-link', html=False)
        self.assertNotContains(response, 'w3-amber', html=False)

    def test_navigation_structure_authenticated_regular_user(self):
        user = self._create_user("navtester")
        self.client.force_login(user)

        response = self.client.get(reverse("index"))

        self.assertNotContains(response, _("Login"))
        self.assertContains(response, _("Logout"))
        expected_user_label = _("User: %(username)s") % {"username": user.get_username()}
        self.assertContains(response, expected_user_label)
        self.assertContains(response, 'form id="logout-form"', html=False)
        self.assertContains(response, 'class="nav-items w3-hide-small"', html=False)
        self.assertContains(response, 'nav-link', html=False)
        self.assertContains(response, 'nav-user-label', html=False)
        self.assertContains(response, 'nav-auth', html=False)
        self.assertNotContains(response, 'data-dropdown-toggle="reports-menu"', html=False)

    def test_reports_menu_visible_for_collection_manager(self):
        user = self._create_user("collection_manager", groups=[self.collection_manager_group])
        self.client.force_login(user)

        response = self.client.get(reverse("index"))

        self.assertContains(response, 'id="reports-menu"', html=False)
        self.assertContains(response, _("Reports"))

    def test_reports_menu_visible_for_superuser(self):
        user = self._create_user("admin", is_superuser=True)
        self.client.force_login(user)

        response = self.client.get(reverse("index"))

        self.assertContains(response, 'id="reports-menu"', html=False)
        self.assertContains(response, _("Reports"))

    def test_reports_views_require_authorised_user(self):
        media_report_url = reverse("media_report")
        accession_report_url = reverse("accession_distribution_report")

        # Anonymous users should be redirected to login
        response = self.client.get(media_report_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('account_login')}?next={media_report_url}")

        # Authenticated users without permissions should also be redirected
        regular_user = self._create_user("regular_user")
        self.client.force_login(regular_user)
        response = self.client.get(media_report_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('account_login')}?next={media_report_url}")

        # Collection Managers should have access
        authorised_user = self._create_user("cm_user", groups=[self.collection_manager_group])
        self.client.force_login(authorised_user)
        response = self.client.get(media_report_url)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(accession_report_url)
        self.assertEqual(response.status_code, 200)
