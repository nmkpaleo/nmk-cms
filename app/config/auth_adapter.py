"""Account policy: local users are provisioned by admins; ORCID may sign up."""

from allauth.account.adapter import DefaultAccountAdapter


class RestrictedAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request, sociallogin=None):
        # A social login (currently ORCID) may create a linked local account.
        # Ordinary username/password signup is admin-only.
        return sociallogin is not None
