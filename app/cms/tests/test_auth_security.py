from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.auth_adapter import OrcidSocialAccountAdapter, RestrictedAccountAdapter
from config.auth_forms import CaptchaLoginForm, CaptchaResetPasswordForm


class AuthPolicyTests(SimpleTestCase):
    def test_local_signup_is_closed(self):
        self.assertFalse(RestrictedAccountAdapter().is_open_for_signup(None))

    def test_orcid_signup_is_allowed(self):
        self.assertTrue(OrcidSocialAccountAdapter().is_open_for_signup(None, SimpleNamespace(account=SimpleNamespace(provider="orcid"))))

    @override_settings(RECAPTCHA_REQUIRED=False)
    def test_captcha_is_not_added_without_keys(self):
        request = RequestFactory().get("/accounts/login/")
        form = CaptchaLoginForm(request=request)
        self.assertNotIn("captcha", form.fields)

    @override_settings(RECAPTCHA_REQUIRED=True)
    def test_captcha_is_added_when_keys_are_configured(self):
        request = RequestFactory().get("/accounts/login/")
        with patch("config.auth_forms.cache.get", return_value=0), patch("config.auth_forms.cache.add"), patch("config.auth_forms.cache.incr", return_value=1):
            form = CaptchaLoginForm(request=request)
        self.assertIn("captcha", form.fields)

    @override_settings(RECAPTCHA_REQUIRED=False, AUTH_RATE_LIMIT_MAX_ATTEMPTS=1)
    def test_rate_limit_rejects_after_threshold(self):
        request = RequestFactory().post("/accounts/password/reset/", data={})
        with patch("config.auth_forms.cache.add", return_value=False), patch("config.auth_forms.cache.incr", return_value=2):
            form = CaptchaResetPasswordForm(request=request)
            with self.assertRaises(ValidationError):
                form._check_rate_limit()

    @override_settings(AUTH_RATE_LIMIT_TRUST_PROXY=True, AUTH_RATE_LIMIT_TRUSTED_PROXIES=("127.0.0.1",))
    def test_rate_limit_trusts_forwarded_for_from_configured_proxy(self):
        request = RequestFactory().post(
            "/accounts/login/",
            data={},
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="198.51.100.7, 127.0.0.1",
        )
        form = CaptchaLoginForm(request=request)
        self.assertEqual(form._client_key(), "auth-rate:login:198.51.100.7")

    @override_settings(AUTH_RATE_LIMIT_TRUST_PROXY=True, AUTH_RATE_LIMIT_TRUSTED_PROXIES=("127.0.0.1",))
    def test_rate_limit_ignores_forwarded_for_from_untrusted_client(self):
        request = RequestFactory().post(
            "/accounts/login/",
            data={},
            REMOTE_ADDR="198.51.100.99",
            HTTP_X_FORWARDED_FOR="203.0.113.42",
        )
        form = CaptchaLoginForm(request=request)
        self.assertEqual(form._client_key(), "auth-rate:login:198.51.100.99")


class AuthPageTests(TestCase):
    @override_settings(
        RECAPTCHA_REQUIRED=True,
        RECAPTCHA_PUBLIC_KEY="test-public-key",
        RECAPTCHA_PRIVATE_KEY="test-private-key",
    )
    def test_login_page_renders_captcha_media(self):
        response = self.client.get(reverse("account_login"))

        self.assertContains(response, "recaptcha/api.js")
        self.assertContains(response, 'id="id_captcha"')
