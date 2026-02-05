from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

INTERNAL_REVIEWER_GROUPS = ["Collection Managers", "Curators"]
EXTERNAL_EXPERT_GROUPS = ["External Experts"]
OVERRIDE_GROUPS = ["Collection Managers"]


def _in_groups(user: AbstractBaseUser, groups: list[str]) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return user.groups.filter(name__in=groups).exists()


def is_internal_reviewer(user: AbstractBaseUser) -> bool:
    return bool(user.is_superuser) or _in_groups(user, INTERNAL_REVIEWER_GROUPS)


def is_external_expert(user: AbstractBaseUser) -> bool:
    return _in_groups(user, EXTERNAL_EXPERT_GROUPS)


def can_approve_specimen_list_page(user: AbstractBaseUser) -> bool:
    return is_internal_reviewer(user)


def can_override_review_lock(user: AbstractBaseUser) -> bool:
    return bool(user.is_superuser) or _in_groups(user, OVERRIDE_GROUPS)
