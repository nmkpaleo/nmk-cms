"""Views supporting merge workflows and per-field selection flows."""
from __future__ import annotations

import json
import logging
from typing import Iterable, Mapping

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Model
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _, ngettext
from django.views import View

from cms.merge import merge_records
from cms.merge.forms import (
    ElementFieldSelectionForm,
    FieldSelectionCandidate,
    FieldSelectionForm,
)
from cms.merge.mixins import MergeMixin
from cms.merge.services import merge_elements
from cms.models import Element


class FieldSelectionMergeView(LoginRequiredMixin, View):
    """Handle per-field merge selection using :class:`FieldSelectionForm`."""

    http_method_names = ["get", "post"]
    form_class = FieldSelectionForm
    model: type[MergeMixin] | None = None
    action_url_name = "merge:merge_field_selection"
    raise_exception = True

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.is_staff:
            return HttpResponse(status=403)
        if not getattr(settings, "MERGE_TOOL_FEATURE", False):
            return HttpResponse(status=503)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        context = self._build_context(request, *args, **kwargs)
        if isinstance(context, HttpResponse):
            return context

        form = context["form"]
        candidates = context["candidates"]
        target = context["target"]

        if self._wants_json(request):
            payload = {
                "fields": [
                    self._serialise_value(
                        {k: v for k, v in option.items() if k != "bound_field"}
                    )
                    for option in form.field_options
                ],
                "target": target.instance.pk,
                "candidates": [candidate.key for candidate in candidates],
            }
            return JsonResponse(payload)

        return render(request, "merge/per_field_strategy.html", context)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        context = self._build_context(request, *args, data=request.POST, **kwargs)
        if isinstance(context, HttpResponse):
            return context
        form = context["form"]
        candidates = context["candidates"]
        target = context["target"]

        if not form.is_valid():
            if self._wants_json(request):
                return JsonResponse({"errors": form.errors}, status=400)
            return render(
                request,
                "merge/per_field_strategy.html",
                context,
                status=400,
            )

        sources = [candidate for candidate in candidates if candidate.role == "source"]
        if not sources:
            return HttpResponseBadRequest("A source record must be provided for merging.")

        merge_results = []
        target_instance = target.instance

        with transaction.atomic():
            for source_candidate in sources:
                merge_result = self.perform_merge(
                    form=form,
                    source=source_candidate.instance,
                    target=target_instance,
                    request=request,
                )
                merge_results.append((source_candidate, merge_result))
                target_instance = merge_result.target

        self._add_success_message(request, target_instance, len(merge_results))

        if self._wants_json(request):
            last_result = merge_results[-1][1]
            return JsonResponse(
                {
                    "target_id": target_instance.pk,
                    "resolved_fields": self._serialise_value(
                        {
                            field: self._serialise_resolution(resolution)
                            for field, resolution in last_result.resolved_values.items()
                        }
                    ),
                    "relation_actions": self._serialise_value(
                        last_result.relation_actions
                    ),
                }
            )

        cancel_url = context.get("cancel_url") or request.META.get("HTTP_REFERER", "")
        if cancel_url and url_has_allowed_host_and_scheme(cancel_url, allowed_hosts={request.get_host()}):
            return redirect(cancel_url)

        meta = target_instance._meta
        try:
            change_url = reverse(
                f"admin:{meta.app_label}_{meta.model_name}_change",
                args=[target_instance.pk],
            )
        except Exception:  # pragma: no cover - defensive fallback
            change_url = ""
        return redirect(change_url or "/")

    def get_model(self, request: HttpRequest) -> type[MergeMixin]:
        if self.model is not None:
            return self.model

        model_label = (request.GET.get("model") or request.POST.get("model") or "").strip()
        if not model_label:
            raise ValueError("A model label must be provided for merge operations.")

        try:
            model = apps.get_model(model_label)
        except (LookupError, ValueError) as exc:
            raise ValueError("Invalid model label supplied.") from exc

        if not issubclass(model, MergeMixin):
            raise TypeError("Merge operations are only supported for MergeMixin models.")
        return model

    def get_mergeable_fields(self, model: type[MergeMixin]):
        fields: list = []
        for field in model._meta.concrete_fields:  # type: ignore[attr-defined]
            if field.primary_key or not getattr(field, "editable", False):
                continue
            fields.append(field)
        return fields

    def _build_context(
        self, request: HttpRequest, *args, data: Mapping[str, object] | None = None, **kwargs
    ) -> dict[str, object] | HttpResponse:
        try:
            model = self.get_model(request)
        except Exception as exc:  # pragma: no cover - defensive
            logging.exception("Exception in get_model")
            return HttpResponseBadRequest(_("An internal error has occurred."))

        if model is Element and not isinstance(self, ElementFieldSelectionView):
            return ElementFieldSelectionView.as_view()(request, *args, **kwargs)

        try:
            candidates, target = self.get_candidates(request, model)
        except Exception as exc:  # pragma: no cover - defensive
            logging.exception("Exception in get_candidates")
            return HttpResponseBadRequest(_("An internal error has occurred."))

        form = self.form_class(
            model=model,
            merge_fields=self.get_mergeable_fields(model),
            candidates=candidates,
            data=data,
        )

        cancel_url = (
            (request.POST.get("cancel") if request.method == "POST" else request.GET.get("cancel"))
            or request.META.get("HTTP_REFERER", "")
        )

        return {
            "form": form,
            "model_label": model._meta.label,
            "target_id": target.key,
            "target": target,
            "candidates": candidates,
            "candidate_ids": ",".join(candidate.key for candidate in candidates),
            "action_url": self.get_action_url(request),
            "cancel_url": cancel_url,
        }

    def get_action_url(self, request: HttpRequest) -> str:
        return reverse(self.action_url_name)

    def perform_merge(
        self,
        *,
        form: FieldSelectionForm,
        source: MergeMixin,
        target: MergeMixin,
        request: HttpRequest,
    ):
        return merge_records(
            source=source,
            target=target,
            strategy_map=form.build_strategy_map(),
            user=request.user,
        )

    def _add_success_message(self, request: HttpRequest, target_instance: MergeMixin, merge_count: int) -> None:
        messages.success(
            request,
            ngettext(
                "Merged %(count)d source into %(target)s using field selections.",
                "Merged %(count)d sources into %(target)s using field selections.",
                merge_count,
            )
            % {"count": merge_count, "target": target_instance},
        )

    def get_candidates(
        self, request: HttpRequest, model: type[MergeMixin]
    ) -> tuple[list[FieldSelectionCandidate], FieldSelectionCandidate]:
        target_id = (request.GET.get("target") or request.POST.get("target") or "").strip()
        ids_param = request.GET.get("candidates") or request.POST.get("candidates") or ""
        candidate_ids = [value for value in (item.strip() for item in ids_param.split(",")) if value]

        if not target_id or not candidate_ids:
            raise ValueError("Merge requests must supply target and candidate identifiers.")
        if target_id not in candidate_ids:
            candidate_ids.insert(0, target_id)

        candidates: list[FieldSelectionCandidate] = []
        target: FieldSelectionCandidate | None = None

        for candidate_id in candidate_ids:
            instance = get_object_or_404(model, pk=candidate_id)
            role = "target" if str(candidate_id) == str(target_id) else "source"
            candidate = FieldSelectionCandidate.from_instance(
                instance, label=str(instance), role=role
            )
            candidates.append(candidate)
            if role == "target":
                target = candidate

        if target is None:
            raise ValueError("A valid target candidate is required.")

        return candidates, target

    def _wants_json(self, request: HttpRequest) -> bool:
        explicit = (request.GET.get("format") or request.POST.get("format") or "").lower()
        if explicit == "json":
            return True
        accept = request.headers.get("Accept", "")
        return "application/json" in accept.split(",")

    def _get_source_candidate(
        self, candidates: Iterable[FieldSelectionCandidate]
    ) -> FieldSelectionCandidate | None:
        for candidate in candidates:
            if candidate.role == "source":
                return candidate
        return None

    def _serialise_resolution(self, resolution: object) -> object:
        if hasattr(resolution, "as_log_payload"):
            payload = resolution.as_log_payload()
        elif isinstance(resolution, Mapping):
            payload = dict(resolution)
        else:
            payload = {"value": resolution}
        return self._serialise_value(payload)

    def _serialise_value(self, value: object) -> object:
        if isinstance(value, Model):
            return getattr(value, "pk", str(value))
        if isinstance(value, Mapping):
            return {k: self._serialise_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._serialise_value(item) for item in value]
        if hasattr(value, "pk"):
            return getattr(value, "pk")

        try:
            return json.loads(json.dumps(value, cls=DjangoJSONEncoder))
        except TypeError:
            return str(value)


class ElementFieldSelectionView(PermissionRequiredMixin, FieldSelectionMergeView):
    """Element-specific per-field merge view backed by :func:`merge_elements`."""

    form_class = ElementFieldSelectionForm
    model = Element
    action_url_name = "merge:merge_element_field_selection"
    permission_required = "cms.can_merge"
    raise_exception = True

    def get_mergeable_fields(self, model: type[MergeMixin]):
        return ElementFieldSelectionForm.get_mergeable_fields(model)

    def get_action_url(self, request: HttpRequest) -> str:
        return reverse(self.action_url_name)

    def perform_merge(
        self,
        *,
        form: ElementFieldSelectionForm,
        source: MergeMixin,
        target: MergeMixin,
        request: HttpRequest,
    ):
        return merge_elements(
            source=source,
            target=target,
            selected_fields=form.build_selected_fields(),
            user=request.user,
        )
