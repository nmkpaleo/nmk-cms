from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.auth_adapter import OrcidSocialAccountAdapter, RestrictedAccountAdapter
from config.auth_forms import CaptchaLoginForm, CaptchaResetPasswordForm


class AuthPolicyTests(TestCase):
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

    @override_settings(RECAPTCHA_REQUIRED=True)
    def test_login_form_rejects_post_without_captcha_token(self):
        request = RequestFactory().post(
            "/accounts/login/",
            data={"login": "user@example.com", "password": "invalid-password"},
        )
        form = CaptchaLoginForm(
            data={"login": "user@example.com", "password": "invalid-password"},
            request=request,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("captcha", form.errors)

    @override_settings(RECAPTCHA_REQUIRED=True)
    def test_password_reset_form_rejects_post_without_captcha_token(self):
        request = RequestFactory().post(
            "/accounts/password/reset/",
            data={"email": "user@example.com"},
        )
        form = CaptchaResetPasswordForm(data={"email": "user@example.com"}, request=request)
        self.assertFalse(form.is_valid())
        self.assertIn("captcha", form.errors)

    @override_settings(RECAPTCHA_REQUIRED=False, AUTH_RATE_LIMIT_MAX_ATTEMPTS=1)
    def test_rate_limit_rejects_after_threshold(self):
        request = RequestFactory().post("/accounts/password/reset/", data={})
        with patch("config.auth_forms.cache.add", return_value=False), patch("config.auth_forms.cache.incr", return_value=2):
            form = CaptchaResetPasswordForm(request=request)
            with self.assertRaises(ValidationError):
                form._check_rate_limit()

    @override_settings(RECAPTCHA_REQUIRED=False, AUTH_RATE_LIMIT_MAX_ATTEMPTS=10)
    def test_rate_limit_recreates_window_when_key_expires_between_cache_ops(self):
        request = RequestFactory().post(
            "/accounts/password/reset/",
            data={"email": "user@example.com"},
        )
        with patch("config.auth_forms.cache.add", side_effect=[False, True]), patch(
            "config.auth_forms.cache.incr", side_effect=ValueError
        ):
            form = CaptchaResetPasswordForm(request=request)
            form._check_rate_limit()

    def test_login_rate_limit_skips_requests_with_field_errors(self):
        request = RequestFactory().post("/accounts/login/", data={})
        with patch.object(CaptchaLoginForm, "_check_rate_limit") as check_rate_limit:
            form = CaptchaLoginForm(data={}, request=request)
            self.assertFalse(form.is_valid())
        check_rate_limit.assert_not_called()

    def test_password_reset_rate_limit_skips_requests_with_field_errors(self):
        request = RequestFactory().post("/accounts/password/reset/", data={"email": "not-an-email"})
        with patch.object(CaptchaResetPasswordForm, "_check_rate_limit") as check_rate_limit:
            form = CaptchaResetPasswordForm(data={"email": "not-an-email"}, request=request)
            self.assertFalse(form.is_valid())
        check_rate_limit.assert_not_called()

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
    @override_settings(RECAPTCHA_REQUIRED=False)
    def test_login_page_uses_custom_form_without_captcha(self):
        response = self.client.get(reverse("account_login"), {"next": "/admin/"})

        self.assertIsInstance(response.context["form"], CaptchaLoginForm)
        self.assertIs(response.context["form"].request, response.wsgi_request)
        self.assertContains(response, 'name="next"')
        self.assertContains(response, 'value="/admin/"')
        self.assertNotContains(response, 'id="id_captcha"')

    @override_settings(
        RECAPTCHA_REQUIRED=True,
        RECAPTCHA_PUBLIC_KEY="test-public-key",
        RECAPTCHA_PRIVATE_KEY="test-private-key",
    )
    def test_login_page_renders_captcha_media(self):
        response = self.client.get(reverse("account_login"))

        self.assertIsInstance(response.context["form"], CaptchaLoginForm)
        self.assertContains(response, "recaptcha/api.js")
        self.assertContains(response, 'id="id_captcha"')

    @override_settings(RECAPTCHA_REQUIRED=False)
    def test_password_reset_page_uses_custom_form_without_captcha(self):
        response = self.client.get(reverse("account_reset_password"))

        self.assertIsInstance(response.context["form"], CaptchaResetPasswordForm)
        self.assertNotContains(response, 'id="id_captcha"')

    @override_settings(
        RECAPTCHA_REQUIRED=True,
        RECAPTCHA_PUBLIC_KEY="test-public-key",
        RECAPTCHA_PRIVATE_KEY="test-private-key",
    )
    def test_password_reset_page_renders_captcha_media(self):
        response = self.client.get(reverse("account_reset_password"))

        self.assertIsInstance(response.context["form"], CaptchaResetPasswordForm)
        self.assertContains(response, "recaptcha/api.js")
        self.assertContains(response, 'id="id_captcha"')

    @override_settings(RECAPTCHA_REQUIRED=False)
    def test_password_reset_valid_post_uses_request_aware_form(self):
        with patch.object(CaptchaResetPasswordForm, "_check_rate_limit", autospec=True) as check_rate_limit:
            response = self.client.post(
                reverse("account_reset_password"),
                data={"email": "unknown@example.com"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("account_reset_password_done"))
        check_rate_limit.assert_called_once()
        self.assertIs(check_rate_limit.call_args.args[0].request, response.wsgi_request)

    @override_settings(RECAPTCHA_REQUIRED=False)
    def test_login_post_enforces_rate_limit_validation_error(self):
        with patch.object(
            CaptchaLoginForm,
            "_check_rate_limit",
            autospec=True,
            side_effect=ValidationError("Too many authentication attempts. Please try again later."),
        ):
            response = self.client.post(
                reverse("account_login"),
                data={"login": "user@example.com", "password": "invalid-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many authentication attempts. Please try again later.")

    @override_settings(RECAPTCHA_REQUIRED=False)
    def test_password_reset_post_enforces_rate_limit_validation_error(self):
        with patch.object(
            CaptchaResetPasswordForm,
            "_check_rate_limit",
            autospec=True,
            side_effect=ValidationError("Too many authentication attempts. Please try again later."),
        ):
            response = self.client.post(
                reverse("account_reset_password"),
                data={"email": "unknown@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many authentication attempts. Please try again later.")
