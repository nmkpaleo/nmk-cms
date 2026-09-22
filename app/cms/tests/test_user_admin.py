from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class UserAdminPasswordChangeTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="Admin-password-123!"
        )
        self.user = get_user_model().objects.create_user(
            username="target-user", email="target@example.com", password="Old-password-123!"
        )
        self.client.force_login(self.admin)

    def test_user_change_page_exposes_password_change_link(self):
        response = self.client.get(reverse("admin:auth_user_change", args=[self.user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:auth_user_password_change", args=[self.user.pk]))

    def test_admin_can_change_user_password(self):
        response = self.client.post(
            reverse("admin:auth_user_password_change", args=[self.user.pk]),
            {"password1": "New-password-123!", "password2": "New-password-123!"},
        )

        self.assertRedirects(response, reverse("admin:auth_user_change", args=[self.user.pk]))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-password-123!"))
        self.assertFalse(self.user.check_password("Old-password-123!"))
