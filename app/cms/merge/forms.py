"""Forms supporting merge workflows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from django import forms
from django.contrib.admin.utils import display_for_field
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .constants import MergeStrategy


@dataclass(frozen=True)
class FieldSelectionCandidate:
    """Representation of a selectable merge candidate."""

    key: str
    label: str
    instance: models.Model
    role: str | None = None

    @classmethod
    def from_instance(
        cls,
        instance: models.Model,
        *,
        label: str | None = None,
        role: str | None = None,
    ) -> "FieldSelectionCandidate":
        if getattr(instance, "pk", None) is None:
            raise ValueError("Merge candidates must have a primary key value.")
        return cls(
            key=str(instance.pk),
            label=label or str(instance),
            instance=instance,
            role=role.lower() if isinstance(role, str) else None,
        )


class FieldSelectionForm(forms.Form):
    """Render mergeable fields with radio selection across multiple candidates."""

    selection_prefix = "select__"

    def __init__(
        self,
        *,
        model: type[models.Model],
        merge_fields: Iterable[models.Field],
        candidates: Iterable[FieldSelectionCandidate | models.Model],
        data: Mapping[str, object] | None = None,
        initial: Mapping[str, object] | None = None,
    ) -> None:
        self.model = model
        self.merge_fields: Sequence[models.Field] = tuple(merge_fields)
        self.candidates = self._normalise_candidates(candidates)
        self._candidate_map = {candidate.key: candidate for candidate in self.candidates}
        self.field_options: list[dict[str, object]] = []
        super().__init__(data=data, initial=initial)
        self._build_fields()

    @classmethod
    def selection_field_name(cls, field_name: str) -> str:
        return f"{cls.selection_prefix}{field_name}"

    def _normalise_candidates(
        self, candidates: Iterable[FieldSelectionCandidate | models.Model]
    ) -> list[FieldSelectionCandidate]:
        normalised: list[FieldSelectionCandidate] = []
        for candidate in candidates:
            if isinstance(candidate, FieldSelectionCandidate):
                resolved = candidate
            elif isinstance(candidate, models.Model):
                resolved = FieldSelectionCandidate.from_instance(candidate)
            else:
                raise TypeError("Candidates must be model instances or FieldSelectionCandidate")

            if not isinstance(resolved.instance, self.model):
                raise TypeError(
                    "Candidates must be instances of the merge model configured for the form."
                )
            normalised.append(resolved)

        if not normalised:
            raise ValueError("At least one merge candidate is required.")

        keys = [candidate.key for candidate in normalised]
        if len(keys) != len(set(keys)):
            raise ValueError("Merge candidates must have unique keys for selection.")

        return normalised

    def _build_fields(self) -> None:
        for field in self.merge_fields:
            choices: list[tuple[str, str]] = []
            choice_rows: list[dict[str, object]] = []
            default_key = None

            for candidate in self.candidates:
                value = field.value_from_object(candidate.instance)
                display = display_for_field(value, field, "—")
                choice_key = candidate.key
                if candidate.role == "target":
                    default_key = choice_key

                choices.append((choice_key, str(display)))
                choice_rows.append(
                    {
                        "key": choice_key,
                        "label": candidate.label,
                        "value": display,
                        "is_target": candidate.role == "target",
                        "field_value": value,
                        "role": candidate.role,
                    }
                )

            field_name = self.selection_field_name(field.name)
            self.fields[field_name] = forms.ChoiceField(
                choices=choices,
                label=field.verbose_name,
                widget=forms.RadioSelect,
                initial=default_key or choices[0][0],
            )

            self.field_options.append(
                {
                    "name": field.name,
                    "label": field.verbose_name,
                    "choices": choice_rows,
                    "field_name": field_name,
                    "bound_field": self[field_name],
                }
            )

    def clean(self) -> Mapping[str, object]:
        cleaned_data = super().clean()
        for field in self.merge_fields:
            field_name = self.selection_field_name(field.name)
            selected_key = cleaned_data.get(field_name)
            if selected_key and selected_key not in self._candidate_map:
                self.add_error(field_name, ValidationError(_("Select a valid option.")))
        return cleaned_data

    def build_strategy_map(self) -> dict[str, object]:
        """Return a strategy payload for :func:`cms.merge.merge_records`."""

        strategy_map: dict[str, object] = {"fields": {}}
        for field in self.merge_fields:
            field_name = field.name
            form_field_name = self.selection_field_name(field_name)
            selected_key = self.cleaned_data.get(form_field_name)
            if not selected_key:
                continue

            candidate = self._candidate_map.get(selected_key)
            if not candidate:
                continue

            payload: dict[str, object] = {"strategy": MergeStrategy.FIELD_SELECTION.value}

            if candidate.role == "target":
                payload["selected_from"] = candidate.role
            else:
                payload["selected_from"] = candidate.role or "source"
                payload["value"] = field.value_from_object(candidate.instance)

            strategy_map["fields"][field_name] = payload

        return strategy_map
