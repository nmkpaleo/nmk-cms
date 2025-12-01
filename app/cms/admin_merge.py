"""Admin integration helpers for managing merge workflows."""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Mapping

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.utils import display_for_field
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, path, reverse
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _, ngettext

from .merge import merge_records
from .merge.constants import MERGE_STRATEGY_CHOICES, MergeStrategy
from .merge.signals import merge_failed

try:  # pragma: no cover - optional dependency
    import sentry_sdk
except Exception:  # pragma: no cover - defensive
    sentry_sdk = None


logger = logging.getLogger(__name__)

MERGE_DISABLED_MESSAGE = _(
    "The merge tool is currently disabled. Contact an administrator if this is unexpected."
)


def manual_value_strategy(
    *,
    field_name: str,
    target: models.Model,
    options: Mapping[str, Any],
    **_: Any,
) -> Any:
    """Return a value resolved from a manual prompt for the given ``field_name``."""

    value = options.get("value")
    try:
        field = target._meta.get_field(field_name)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive guard
        return value

    if isinstance(field, models.ForeignKey):
        if value in (None, ""):
            return None
        return field.remote_field.model._default_manager.get(pk=value)

    return value


class MergeAdminForm(forms.Form):
    """Form rendered by :class:`MergeAdminMixin` to configure merges."""

    selected_ids = forms.CharField(required=False, widget=forms.HiddenInput)
    source = forms.CharField(required=True, widget=forms.HiddenInput)
    target = forms.CharField(required=True, widget=forms.HiddenInput)

    strategy_prefix = "strategy__"
    value_prefix = "value__"

    def __init__(
        self,
        *,
        model: type[models.Model],
        merge_fields: Iterable[models.Field],
        data: Mapping[str, Any] | None = None,
        initial: Mapping[str, Any] | None = None,
    ) -> None:
        self.model = model
        self._merge_fields: List[models.Field] = list(merge_fields)
        self.field_configs: list[dict[str, Any]] = []
        super().__init__(data=data, initial=initial)

        for field in self._merge_fields:
            strategy_name = self.strategy_field_name(field.name)
            manual_name = self.value_field_name(field.name)

            default_strategy = MergeStrategy.PREFER_NON_NULL
            if hasattr(model, "get_merge_strategy_for_field"):
                raw_default = model.get_merge_strategy_for_field(field.name)
                try:
                    default_strategy = (
                        raw_default
                        if isinstance(raw_default, MergeStrategy)
                        else MergeStrategy(raw_default)
                    )
                except ValueError:
                    default_strategy = MergeStrategy.PREFER_NON_NULL

            self.fields[strategy_name] = forms.ChoiceField(
                choices=MERGE_STRATEGY_CHOICES,
                initial=default_strategy.value,
                label=field.verbose_name,
            )

            manual_field = field.formfield(required=False)
            if manual_field is None:
                manual_field = forms.CharField(required=False, label=field.verbose_name)
            manual_field.widget.attrs.setdefault("class", "vTextField")
            manual_field.label = _("Manual value")
            self.fields[manual_name] = manual_field

            self.field_configs.append(
                {
                    "field": field,
                    "strategy_name": strategy_name,
                    "value_name": manual_name,
                }
            )

    @classmethod
    def strategy_field_name(cls, field_name: str) -> str:
        return f"{cls.strategy_prefix}{field_name}"

    @classmethod
    def value_field_name(cls, field_name: str) -> str:
        return f"{cls.value_prefix}{field_name}"

    def clean_source(self) -> models.Model:
        return self._clean_object_field("source")

    def clean_target(self) -> models.Model:
        return self._clean_object_field("target")

    def _clean_object_field(self, field_name: str) -> models.Model:
        raw_value = self.cleaned_data.get(field_name)
        if not raw_value:
            raise ValidationError(_("Select a record."))
        try:
            return self.model._default_manager.get(pk=raw_value)
        except self.model.DoesNotExist as exc:  # type: ignore[attr-defined]
            raise ValidationError(_("Selected record no longer exists.")) from exc

    def clean(self) -> Mapping[str, Any]:
        cleaned_data = super().clean()

        source = cleaned_data.get("source")
        target = cleaned_data.get("target")
        if source and target and getattr(source, "pk", None) == getattr(target, "pk", None):
            raise ValidationError(_("Source and target must be different records."))

        raw_ids = cleaned_data.get("selected_ids") or ""
        self.selected_ids = [value for value in (item.strip() for item in raw_ids.split(",")) if value]

        for config in self.field_configs:
            strategy_name = config["strategy_name"]
            value_name = config["value_name"]
            raw_strategy = cleaned_data.get(strategy_name)
            if not raw_strategy:
                continue
            try:
                strategy = MergeStrategy(raw_strategy)
            except ValueError as exc:  # pragma: no cover - defensive guard
                raise ValidationError(_("Unknown merge strategy specified.")) from exc

            cleaned_data[strategy_name] = strategy.value
            if strategy is MergeStrategy.USER_PROMPT:
                manual_value = cleaned_data.get(value_name)
                if manual_value in (None, ""):
                    self.add_error(
                        value_name,
                        _("Provide a value when using the USER_PROMPT strategy."),
                    )
                elif isinstance(manual_value, models.Model):
                    cleaned_data[value_name] = manual_value.pk

        return cleaned_data

    def build_strategy_map(self) -> dict[str, Any]:
        """Return a strategy payload suitable for :func:`merge_records`."""

        strategies: dict[str, Any] = {"fields": {}}
        for config in self.field_configs:
            field = config["field"]
            field_name = field.name
            strategy_value = self.cleaned_data.get(config["strategy_name"])
            if not strategy_value:
                continue

            strategy = MergeStrategy(strategy_value)
            if strategy is MergeStrategy.USER_PROMPT:
                manual_value = self.cleaned_data.get(config["value_name"])
                strategies["fields"][field_name] = {
                    "strategy": MergeStrategy.CUSTOM.value,
                    "callback": manual_value_strategy,
                    "value": manual_value,
                }
            else:
                strategies["fields"][field_name] = strategy.value

        return strategies

    def get_bound_instance(self, role: str) -> models.Model | None:
        """Return the instance currently selected for ``role`` (source/target)."""

        value = self.data.get(role) if self.is_bound else self.initial.get(role)
        if not value:
            return None
        try:
            return self.model._default_manager.get(pk=value)
        except self.model.DoesNotExist:  # type: ignore[attr-defined]
            return None


class MergeAdminMixin:
    """Reusable admin mixin exposing merge tooling within the Django admin."""

    merge_template = "admin/cms/merge/merge_form.html"
    merge_form_class = MergeAdminForm

    class Media:
        js = ("cms/js/merge_admin.js",)

    def is_merge_tool_enabled(self) -> bool:
        """Return ``True`` when the merge tooling is enabled via settings."""

        return getattr(settings, "MERGE_TOOL_FEATURE", False)

    @admin.action(description=_("Merge selected records"))
    def merge_selected(self, request, queryset):  # type: ignore[override]
        if not self.is_merge_tool_enabled():
            self.message_user(request, MERGE_DISABLED_MESSAGE, level=messages.WARNING)
            return None
        if not self.has_merge_permission(request):
            self.message_user(
                request,
                _("You do not have permission to merge records."),
                level=messages.ERROR,
            )
            return None

        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        if len(selected) < 2:
            self.message_user(
                request,
                _("Select at least two records to start a merge."),
                level=messages.WARNING,
            )
            return None

        info = self.model._meta.app_label, self.model._meta.model_name
        url = reverse(f"admin:{info[0]}_{info[1]}_merge")
        return HttpResponseRedirect(f"{url}?ids={','.join(selected)}")

    def get_actions(self, request):  # type: ignore[override]
        actions = super().get_actions(request)
        if not self.is_merge_tool_enabled() or not self.has_merge_permission(request):
            actions.pop("merge_selected", None)
        return actions

    def has_merge_permission(self, request: HttpRequest) -> bool:
        if not self.is_merge_tool_enabled():
            return False
        opts = self.model._meta
        return request.user.has_perm(f"{opts.app_label}.can_merge")

    def get_mergeable_fields(self) -> list[models.Field]:
        if not self.is_merge_tool_enabled():
            return []
        fields: list[models.Field] = []
        for field in self.model._meta.concrete_fields:  # type: ignore[attr-defined]
            if field.primary_key or not getattr(field, "editable", False):
                continue
            fields.append(field)
        return fields

    def get_urls(self):  # type: ignore[override]
        urls = super().get_urls()
        if not self.is_merge_tool_enabled():
            return urls
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                "merge/",
                self.admin_site.admin_view(self.merge_view),
                name=f"{info[0]}_{info[1]}_merge",
            ),
        ]
        return custom + urls

    def merge_view(self, request: HttpRequest) -> HttpResponse:
        if not self.is_merge_tool_enabled():
            self.message_user(request, MERGE_DISABLED_MESSAGE, level=messages.WARNING)
            info = self.model._meta.app_label, self.model._meta.model_name
            return redirect(f"admin:{info[0]}_{info[1]}_changelist")
        if not self.has_merge_permission(request):
            self.message_user(
                request,
                _("You do not have permission to merge records."),
                level=messages.ERROR,
            )
            info = self.model._meta.app_label, self.model._meta.model_name
            return redirect(f"admin:{info[0]}_{info[1]}_changelist")

        merge_fields = self.get_mergeable_fields()
        selected_ids = self._extract_selected_ids(request)

        initial_source = request.GET.get("source") or (selected_ids[1] if len(selected_ids) > 1 else "")
        initial_target = request.GET.get("target") or (selected_ids[0] if selected_ids else "")

        if request.method == "POST":
            form = self.merge_form_class(
                model=self.model,
                merge_fields=merge_fields,
                data=request.POST,
            )
        else:
            initial: dict[str, Any] = {"selected_ids": ",".join(selected_ids)}
            if initial_source:
                initial["source"] = initial_source
            if initial_target:
                initial["target"] = initial_target

            target_obj = self._get_object_or_none(initial_target)
            if target_obj is not None:
                for field in merge_fields:
                    initial[self.merge_form_class.value_field_name(field.name)] = getattr(
                        target_obj, field.name
                    )

            form = self.merge_form_class(
                model=self.model,
                merge_fields=merge_fields,
                initial=initial,
            )

        source_obj = form.get_bound_instance("source")
        target_obj = form.get_bound_instance("target")

        if request.method == "POST" and form.is_valid():
            try:
                merge_result = merge_records(
                    form.cleaned_data["source"],
                    form.cleaned_data["target"],
                    form.build_strategy_map(),
                    user=request.user,
                )
            except Exception as exc:  # pragma: no cover - surfaced to admin UI
                source = form.cleaned_data.get("source")
                target = form.cleaned_data.get("target")
                logger.exception(
                    "Merge failed for %s into %s", source, target, exc_info=exc
                )
                merge_failed.send(
                    sender=self.__class__,
                    request=request,
                    source=source,
                    target=target,
                    error=exc,
                )
                if sentry_sdk is not None:  # pragma: no cover - optional dependency
                    sentry_sdk.add_breadcrumb(
                        category="merge",
                        message="Merge operation failed",
                        level="error",
                        data={
                            "model": f"{self.model._meta.app_label}.{self.model._meta.model_name}",
                            "source": getattr(source, "pk", None),
                            "target": getattr(target, "pk", None),
                        },
                    )
                    sentry_sdk.capture_exception(exc)
                self.message_user(request, str(exc), level=messages.ERROR)
            else:
                target = merge_result.target
                source = form.cleaned_data["source"]
                base_message = _(
                    "Merged %(source)s into %(target)s (%(count)s fields updated)."
                ) % {
                    "source": source,
                    "target": target,
                    "count": len(merge_result.resolved_values),
                }
                self.log_change(
                    request,
                    target,
                    f"Merged {source.pk} into {target.pk}",
                )
                self.message_user(
                    request,
                    base_message,
                    level=messages.SUCCESS,
                )
                relation_summary_text = self._relation_summary_text(
                    [merge_result.relation_actions]
                )
                if relation_summary_text:
                    self.message_user(
                        request,
                        _("Relation updates: %(summary)s")
                        % {"summary": relation_summary_text},
                        level=messages.INFO,
                    )
                info = self.model._meta.app_label, self.model._meta.model_name
                return redirect(f"admin:{info[0]}_{info[1]}_change", target.pk)

        context = self._build_merge_context(
            request,
            form=form,
            selected_ids=selected_ids,
            source_obj=source_obj,
            target_obj=target_obj,
            merge_fields=merge_fields,
        )
        return render(request, self.merge_template, context)

    def _extract_selected_ids(self, request: HttpRequest) -> list[str]:
        raw = request.GET.get("ids") or request.POST.get("selected_ids") or ""
        return [value for value in (item.strip() for item in raw.split(",")) if value]

    def _get_object_or_none(self, pk: str | None) -> models.Model | None:
        if not pk:
            return None
        try:
            return self.model._default_manager.get(pk=pk)
        except self.model.DoesNotExist:  # type: ignore[attr-defined]
            return None

    def _build_merge_context(
        self,
        request: HttpRequest,
        *,
        form: MergeAdminForm,
        selected_ids: list[str],
        source_obj: models.Model | None,
        target_obj: models.Model | None,
        merge_fields: Iterable[models.Field],
    ) -> dict[str, Any]:
        opts = self.model._meta
        changelist_url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")

        selected_objects = self._serialise_objects(selected_ids)

        field_rows = []
        for config in form.field_configs:
            field = config["field"]
            field_rows.append(
                {
                    "name": field.name,
                    "label": field.verbose_name,
                    "source": self._format_field_value(source_obj, field),
                    "target": self._format_field_value(target_obj, field),
                    "strategy": form[config["strategy_name"]],
                    "manual": form[config["value_name"]],
                }
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": opts,
            "form": form,
            "media": self.media + form.media,
            "title": _(f"Merge {opts.verbose_name}"),
            "field_rows": field_rows,
            "selected_objects": selected_objects,
            "source_summary": self._serialise_instance(source_obj),
            "target_summary": self._serialise_instance(target_obj),
            "changelist_url": changelist_url,
            "search_url": self._safe_reverse("merge:merge_candidate_search"),
            "field_selection_url": self._safe_reverse("merge:merge_field_selection"),
            "field_selection_help": _(
                "Use the Field selection strategy when you need to pick a value "
                "for each field. If you choose it here without providing per-field "
                "selections, the merge will keep the existing target values."
            ),
            "model_label": f"{opts.app_label}.{opts.model_name}",
        }
        return context

    def _safe_reverse(self, url_name: str) -> str:
        if not self.is_merge_tool_enabled():
            return ""
        try:
            return reverse(url_name)
        except NoReverseMatch:
            if url_name == "merge:merge_candidate_search":
                return "/merge/search/"
            if url_name == "merge:merge_field_selection":
                return "/merge/field-selection/"
            return ""

    def _relation_summary_text(
        self,
        relation_logs: Iterable[Mapping[str, Mapping[str, Any]]],
    ) -> str:
        return "; ".join(self._summarize_relation_actions(relation_logs))

    def _summarize_relation_actions(
        self,
        relation_logs: Iterable[Mapping[str, Mapping[str, Any]]],
    ) -> list[str]:
        totals: dict[str, dict[str, int | str]] = {}
        for relation_actions in relation_logs:
            for name, payload in relation_actions.items():
                aggregate = totals.setdefault(name, {"action": payload.get("action", "")})
                for key in ("updated", "added", "deleted", "would_delete", "skipped"):
                    value = payload.get(key)
                    if isinstance(value, int):
                        aggregate[key] = int(aggregate.get(key, 0)) + value

        summaries: list[str] = []
        for name, aggregate in totals.items():
            label = self._relation_label(name)
            fragments: list[str] = []
            for key, singular, plural in (
                ("updated", "%(count)d updated", "%(count)d updated"),
                ("added", "%(count)d added", "%(count)d added"),
                ("deleted", "%(count)d deleted", "%(count)d deleted"),
                ("would_delete", "%(count)d would delete", "%(count)d would delete"),
                ("skipped", "%(count)d skipped", "%(count)d skipped"),
            ):
                count = int(aggregate.get(key, 0) or 0)
                if count:
                    fragments.append(
                        ngettext(singular, plural, count) % {"count": count}
                    )

            action_value = aggregate.get("action")
            if not fragments and action_value:
                fragments.append(str(action_value))

            if fragments:
                summaries.append(f"{label} — {', '.join(fragments)}")

        return summaries

    def _relation_label(self, relation_name: str) -> str:
        try:
            field = self.model._meta.get_field(relation_name)
            verbose = getattr(field, "verbose_name", relation_name)
        except Exception:
            verbose = relation_name.replace("_", " ")
        return capfirst(str(verbose))

    def _serialise_objects(self, ids: Iterable[str]) -> list[dict[str, Any]]:
        objects = self.model._default_manager.filter(pk__in=ids)
        mapping = {str(obj.pk): obj for obj in objects}
        ordered: list[dict[str, Any]] = []
        for pk in ids:
            obj = mapping.get(pk)
            if obj is None:
                continue
            ordered.append(self._serialise_instance(obj))
        return ordered

    def _serialise_instance(self, obj: models.Model | None) -> dict[str, Any] | None:
        if obj is None:
            return None
        preview = []
        if hasattr(obj, "get_merge_display_fields"):
            try:
                field_names = list(obj.get_merge_display_fields())
            except Exception:  # pragma: no cover - defensive
                field_names = []
        else:
            field_names = []

        for name in field_names:
            try:
                field = obj._meta.get_field(name)  # type: ignore[attr-defined]
                value = getattr(obj, name, None)
                preview.append(
                    {
                        "field": field.verbose_name,
                        "value": self._format_field_value(obj, field),
                    }
                )
            except Exception:
                value = getattr(obj, name, None)
                preview.append({"field": name, "value": "" if value is None else str(value)})

        return {
            "pk": obj.pk,
            "label": str(obj),
            "preview": preview,
        }

    def _format_field_value(self, obj: models.Model | None, field: models.Field) -> str:
        if obj is None:
            return "—"
        value = getattr(obj, field.name, None)
        if value in (None, ""):
            return "—"
        try:
            return str(display_for_field(value, field))
        except Exception:  # pragma: no cover - safety net
            return str(value)

