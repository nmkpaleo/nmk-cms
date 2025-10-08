"""Reusable mixins that provide merge behaviour to Django models."""
from __future__ import annotations

from typing import Any, ClassVar, Dict, Iterable, MutableMapping

from django.db import models

from .constants import DEFAULT_FIELD_STRATEGY, DEFAULT_RELATION_STRATEGY, MergeStrategy
from .serializers import serialize_instance


class MergeMixin(models.Model):
    """Abstract model that exposes hooks required by the merge workflow."""

    #: Mapping of field names to merge strategies. Sub-classes can override this
    #: to fine tune default behaviour for individual fields.
    merge_fields: ClassVar[MutableMapping[str, MergeStrategy | str]] = {}

    #: Mapping of relation field names to handling directives.
    #:
    #: Each entry can be one of the following:
    #:
    #: - ``"reassign"``: repoint FK/one-to-one relations from the source to the
    #:   merge target.
    #: - ``"merge"``: combine many-to-many memberships.
    #: - ``"skip"``: leave the relation untouched.
    #: - ``MergeStrategy`` value or dictionary containing ``{"strategy": ...}``
    #:   to preserve backwards compatibility with strategy based merging.
    #: - Callable accepting ``relation_name``, ``field``, ``source``, ``target``,
    #:   ``dry_run`` and ``options`` keyword arguments for bespoke behaviour.
    relation_strategies: ClassVar[MutableMapping[str, Any]] = {}

    class Meta:
        abstract = True

    @classmethod
    def get_merge_strategy_for_field(cls, field_name: str) -> MergeStrategy | str:
        """Return the strategy that should be applied to a concrete field."""

        return cls.merge_fields.get(field_name, DEFAULT_FIELD_STRATEGY)

    @classmethod
    def get_relation_strategy(cls, relation_name: str) -> Any:
        """Return the strategy to use for relations when merging records."""

        return cls.relation_strategies.get(relation_name, DEFAULT_RELATION_STRATEGY)

    def get_merge_display_fields(self) -> Iterable[str]:
        """
        Return a list of field names to display in merge previews.

        By default the method returns the first five editable concrete fields
        excluding the primary key. Projects can override this to surface the
        most meaningful identifiers.
        """

        candidates: list[str] = []
        for field in self._meta.concrete_fields:  # type: ignore[attr-defined]
            if not getattr(field, "editable", False):
                continue
            if field.primary_key:
                continue
            candidates.append(field.name)
            if len(candidates) >= 5:
                break
        return candidates

    def snapshot_before_merge(self) -> Dict[str, Any]:
        """Return a serialised snapshot of the record before merging."""

        return serialize_instance(self)

    def archive_source_instance(self, source_instance: "MergeMixin") -> None:
        """
        Hook that allows sub-classes to archive or deactivate the source record.

        The default implementation is a stub to keep the mixin opt-in friendly;
        projects can override when they want to soft-delete or otherwise record
        the outcome of the merge.
        """

        return None
