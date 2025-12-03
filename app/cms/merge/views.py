"""Views supporting merge workflows and per-field selection flows."""
from __future__ import annotations

from typing import Iterable, Mapping

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Model
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, ngettext
from django.views import View

from cms.merge import merge_records
from cms.merge.forms import FieldSelectionCandidate, FieldSelectionForm
from cms.merge.mixins import MergeMixin


class FieldSelectionMergeView(LoginRequiredMixin, View):
    """Handle per-field merge selection using :class:`FieldSelectionForm`."""

    http_method_names = ["get", "post"]
    form_class = FieldSelectionForm
    model: type[MergeMixin] | None = None
    raise_exception = True

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.is_staff:
            return HttpResponse(status=403)
        if not getattr(settings, "MERGE_TOOL_FEATURE", False):
            return HttpResponse(status=503)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            model = self.get_model(request)
            candidates, target = self.get_candidates(request, model)
        except Exception as exc:  # pragma: no cover - defensive
            return HttpResponseBadRequest(str(exc))
        form = self.form_class(
            model=model,
            merge_fields=self.get_mergeable_fields(model),
            candidates=candidates,
        )

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

        return render(
            request,
            "merge/per_field_strategy.html",
            {
                "form": form,
                "model_label": model._meta.label,
                "target_id": target.key,
                "candidate_ids": ",".join(candidate.key for candidate in candidates),
                "action_url": reverse("merge:merge_field_selection"),
                "cancel_url": request.GET.get("cancel") or request.META.get("HTTP_REFERER", ""),
            },
        )

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            model = self.get_model(request)
            candidates, target = self.get_candidates(request, model)
        except Exception as exc:  # pragma: no cover - defensive
            return HttpResponseBadRequest(str(exc))

        form = self.form_class(
            model=model,
            merge_fields=self.get_mergeable_fields(model),
            candidates=candidates,
            data=request.POST,
        )

        if not form.is_valid():
            if self._wants_json(request):
                return JsonResponse({"errors": form.errors}, status=400)
            return render(
                request,
                "merge/per_field_strategy.html",
                {
                    "form": form,
                    "model_label": model._meta.label,
                    "target_id": target.key,
                    "candidate_ids": ",".join(candidate.key for candidate in candidates),
                    "action_url": reverse("merge:merge_field_selection"),
                    "cancel_url": request.POST.get("cancel")
                    or request.META.get("HTTP_REFERER", ""),
                },
                status=400,
            )

        sources = [candidate for candidate in candidates if candidate.role == "source"]
        if not sources:
            return HttpResponseBadRequest("A source record must be provided for merging.")

        strategy_map = form.build_strategy_map()
        merge_results = []
        target_instance = target.instance

        with transaction.atomic():
            for source_candidate in sources:
                merge_result = merge_records(
                    source=source_candidate.instance,
                    target=target_instance,
                    strategy_map=strategy_map,
                    user=request.user,
                )
                merge_results.append((source_candidate, merge_result))
                target_instance = merge_result.target

        messages.success(
            request,
            ngettext(
                "Merged %(count)d source into %(target)s using field selections.",
                "Merged %(count)d sources into %(target)s using field selections.",
                len(merge_results),
            )
            % {"count": len(merge_results), "target": target_instance},
        )

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

        meta = target_instance._meta
        try:
            change_url = reverse(
                f"admin:{meta.app_label}_{meta.model_name}_change",
                args=[target_instance.pk],
            )
        except Exception:  # pragma: no cover - defensive fallback
            change_url = request.POST.get("cancel") or request.META.get("HTTP_REFERER", "")
        return redirect(change_url)

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
            json.dumps(value, cls=DjangoJSONEncoder)
            return value
        except TypeError:
            return str(value)

