"""Account policies for local and ORCID authentication."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class RestrictedAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request, sociallogin=None):
        # Ordinary username/password signup is admin-only. Social signup is
        # handled by the social adapter below.
        return False


class OrcidSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        # ORCID is the sole supported self-service account-creation path.
        return True
