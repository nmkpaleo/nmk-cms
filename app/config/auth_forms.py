"""Allauth forms with optional server-side CAPTCHA protection."""

from allauth.account.forms import LoginForm, ResetPasswordForm
from django.conf import settings

from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Checkbox


class CaptchaMixin:
    """Add a CAPTCHA only when production has configured its credentials."""

    def _add_captcha(self):
        if settings.RECAPTCHA_REQUIRED:
            self.fields["captcha"] = ReCaptchaField(
                widget=ReCaptchaV2Checkbox(),
                label="",
            )


class CaptchaLoginForm(CaptchaMixin, LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_captcha()


class CaptchaResetPasswordForm(CaptchaMixin, ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_captcha()

