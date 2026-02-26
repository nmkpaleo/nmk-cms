from django.test import TestCase
from django.urls import reverse


class AccountTemplateW3Tests(TestCase):
    def test_login_template_uses_w3_components(self):
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        expected_tokens = [
            "w3-container w3-padding-64 w3-sand",
            "w3-card w3-white",
            "w3-round-xlarge",
            "w3-animate-opacity",
        ]
        for token in expected_tokens:
            with self.subTest(token=token):
                self.assertContains(response, token, html=False)
        self.assertNotContains(response, "Login__container", html=False)

    def test_signup_template_uses_w3_components(self):
        response = self.client.get(reverse("account_signup"))

        self.assertEqual(response.status_code, 200)
        expected_tokens = [
            "w3-container w3-padding-64 w3-sand",
            "w3-card w3-white",
            "w3-round-xlarge",
            "w3-animate-opacity",
        ]
        for token in expected_tokens:
            with self.subTest(token=token):
                self.assertContains(response, token, html=False)
        self.assertNotContains(response, "Signup__container", html=False)
