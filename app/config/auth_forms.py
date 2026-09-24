"""Allauth forms with CAPTCHA and abuse-resistance controls."""

import ipaddress
import logging

from allauth.account.adapter import get_adapter
from allauth.account.internal import flows
from allauth.account.forms import default_token_generator
from allauth.account.forms import LoginForm, ResetPasswordForm
from django import forms
from django.conf import settings
from django.core.cache import cache
from allauth.socialaccount.models import SocialAccount
from django.core.exceptions import ValidationError

from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox


logger = logging.getLogger("security.auth")


class AbuseProtectionMixin:
    rate_limit_name = "auth"

    def _client_key(self):
        request = self.request
        client = request.META.get("REMOTE_ADDR", "unknown")
        trusted_proxies = set(settings.AUTH_RATE_LIMIT_TRUSTED_PROXIES)
        if settings.AUTH_RATE_LIMIT_TRUST_PROXY and client in trusted_proxies:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            candidate = forwarded.split(",", 1)[0].strip() if forwarded else ""
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                candidate = ""
            client = candidate or client
        return f"auth-rate:{self.rate_limit_name}:{client}"

    def _check_rate_limit(self):
        key = self._client_key()
        if cache.add(key, 1, settings.AUTH_RATE_LIMIT_WINDOW_SECONDS):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:
                # The key can expire between add() and incr(); recreate it.
                if cache.add(key, 1, settings.AUTH_RATE_LIMIT_WINDOW_SECONDS):
                    count = 1
                else:
                    count = cache.incr(key)
        if count > settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS:
            logger.warning("authentication rate limit exceeded", extra={"flow": self.rate_limit_name})
            raise ValidationError("Too many authentication attempts. Please try again later.")
        if count >= settings.AUTH_RATE_LIMIT_LOG_THRESHOLD:
            logger.warning("repeated authentication attempt", extra={"flow": self.rate_limit_name, "count": count})

class CaptchaMixin:
    """Add a CAPTCHA only when production has configured its credentials."""

    def _add_captcha(self):
        if settings.RECAPTCHA_REQUIRED:
            self.fields["captcha"] = ReCaptchaField(widget=ReCaptchaV2Checkbox(), label="")


class CaptchaLoginForm(AbuseProtectionMixin, CaptchaMixin, LoginForm):
    rate_limit_name = "login"

    def __init__(self, *args, **kwargs):
        request = kwargs.get("request")
        super().__init__(*args, **kwargs)
        self.request = getattr(self, "request", None) or request
        self._add_captcha()

    def clean(self):
        if self.data.get("login") and self.data.get("password"):
            self._check_rate_limit()
        return super().clean()


class CaptchaResetPasswordForm(AbuseProtectionMixin, CaptchaMixin, ResetPasswordForm):
    rate_limit_name = "password-reset"

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        self.request = getattr(self, "request", None) or request
        self._add_captcha()

    def clean(self):
        cleaned_data = super().clean()
        if self.errors and "__all__" not in self.errors:
            return cleaned_data
        self._check_rate_limit()
        return cleaned_data

    def save(self, request, **kwargs):
        """Send reset links only to local-password accounts."""
        orcid_user_ids = set(
            SocialAccount.objects.filter(provider="orcid", user__in=self.users)
            .values_list("user_id", flat=True)
        )
        local_users = [user for user in self.users if user.pk not in orcid_user_ids]
        email = self.cleaned_data["email"]
        token_generator = kwargs.get("token_generator", default_token_generator)
        if local_users or not self.users:
            flows.password_reset.request_password_reset(request, email, local_users, token_generator)
        adapter = get_adapter()
        for user in self.users:
            if user.pk in orcid_user_ids:
                adapter.send_mail(
                    "account/email/orcid_password_reset_not_applicable",
                    email,
                    {"user": user, "request": request},
                )
        return email
