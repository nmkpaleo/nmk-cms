"""Allauth forms with CAPTCHA and abuse-resistance controls."""

import logging

from allauth.account.adapter import get_adapter
from allauth.account.forms import LoginForm, ResetPasswordForm
from django import forms
from django.conf import settings
from django.core.cache import cache

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
            client = forwarded.split(",", 1)[0].strip() if forwarded else client
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
            raise get_adapter(self.request).validation_error(
                "Too many authentication attempts. Please try again later."
            )
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
        if self.errors:
            return self.cleaned_data
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
        if self.errors:
            return self.cleaned_data
        cleaned_data = super().clean()
        self._check_rate_limit()
        return cleaned_data
