"""Allauth view overrides for request-aware form wiring."""

from allauth.account.views import PasswordResetView


class RequestAwarePasswordResetView(PasswordResetView):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs
