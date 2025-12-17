import csv
import io
import posixpath
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List
from xml.etree import ElementTree

from tablib import Dataset
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.forms.widgets import (
    CheckboxInput,
    CheckboxSelectMultiple,
    ClearableFileInput,
    RadioSelect,
    Select,
    SelectMultiple,
    Textarea,
)
from django_select2 import forms as s2forms
from django_select2.forms import (
    ModelSelect2TagWidget,
    ModelSelect2Widget,
    Select2Widget,
)
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from .models import (
    Accession,
    AccessionFieldSlip,
    AccessionNumberSeries,
    AccessionReference,
    AccessionRow,
    Collection,
    Comment,
    Element,
    FieldSlip,
    Identification,
    Locality,
    Organisation,
    Place,
    Media,
    NatureOfSpecimen,
    Person,
    Preparation,
    Reference,
    SpecimenGeology,
    DrawerRegister,
    UserOrganisation,
    Storage,
    Taxon,
    TaxonRank,
    TaxonStatus,
    _resolve_user_organisation,
)

import json

from cms.manual_import import (
    ManualImportError,
    import_manual_row,
    parse_accession_number,
)
from cms.merge.forms import FieldSelectionCandidate, FieldSelectionForm
from cms.utils import coerce_stripped

User = get_user_model()


class W3StyleMixin:
    """Apply W3.CSS-friendly classes to rendered form widgets."""

    _text_input_types = {
        "text",
        "email",
        "number",
        "password",
        "url",
        "search",
        "tel",
        "date",
        "datetime-local",
        "time",
        "month",
        "week",
        "color",
    }
    _input_class = "w3-input w3-border w3-round-large"
    _select_class = "w3-select w3-border w3-round-large"
    _checkbox_class = "w3-check"
    _radio_class = "w3-radio"

    _select2_widgets = (
        Select2Widget,
        ModelSelect2Widget,
        ModelSelect2TagWidget,
    )

    def _merge_widget_class(self, widget: forms.Widget, class_name: str) -> None:
        existing = widget.attrs.get("class", "")
        classes = {c for c in existing.split(" ") if c}
        classes.update(class_name.split(" "))
        widget.attrs["class"] = " ".join(sorted(classes))

    def _apply_w3_styles(self) -> None:
        for field in self.fields.values():
            widget = field.widget

            if isinstance(widget, self._select2_widgets):
                # Select2 renders its own markup; avoid overriding classes.
                continue

            input_type = getattr(widget, "input_type", "")

            if input_type in self._text_input_types:
                self._merge_widget_class(widget, self._input_class)
                continue

            if isinstance(widget, Textarea):
                self._merge_widget_class(widget, self._input_class)
                continue

            if isinstance(widget, (Select, SelectMultiple)):
                self._merge_widget_class(widget, self._select_class)
                continue

            if isinstance(widget, CheckboxInput):
                self._merge_widget_class(widget, self._checkbox_class)
                continue

            if isinstance(widget, CheckboxSelectMultiple):
                self._merge_widget_class(widget, "w3-ul w3-border w3-round-large")
                continue

            if isinstance(widget, RadioSelect):
                self._merge_widget_class(widget, self._radio_class)
                continue

            if isinstance(widget, ClearableFileInput):
                self._merge_widget_class(widget, self._input_class)


class BaseW3Form(W3StyleMixin, forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        self._apply_w3_styles()


class BaseW3ModelForm(W3StyleMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        self._apply_w3_styles()


class AccessionBatchForm(BaseW3Form):
    user = forms.ModelChoiceField(queryset=User.objects.all())
    count = forms.IntegerField(min_value=1, max_value=500)
    collection = forms.ModelChoiceField(queryset=Collection.objects.all())
    specimen_prefix = forms.ModelChoiceField(queryset=Locality.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_users = User.objects.filter(accession_series__is_active=True).distinct()
        self.fields["user"].queryset = active_users.order_by("username")
        self.fields["user"].help_text = (
            "Only users with active accession number series are shown."
        )
        self.fields["user"].label_from_instance = self.user_label_with_remaining

    def user_label_with_remaining(self, user):
        series = user.accession_series.filter(is_active=True).first()
        if series:
            remaining = series.end_at - series.current_number + 1
            return f"{user.get_full_name() or user.username} ({remaining} accessions available)"
        return user.get_full_name() or user.username


class AccessionNumberSelectForm(BaseW3Form):
    accession_number = forms.ChoiceField(label="Select Accession Number", choices=[])

    def __init__(self, *args, **kwargs):
        available_numbers = kwargs.pop("available_numbers", [])
        super().__init__(*args, **kwargs)
        self.fields["accession_number"].choices = [(n, n) for n in available_numbers]


class UserOrganisationSelect(forms.Select):
    """Select widget that exposes the user's organisation for client-side filtering."""

    def __init__(self, *args, user_org_map: dict[str, str] | None = None, **kwargs):
        self.user_org_map = user_org_map or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value:
            organisation_id = self.user_org_map.get(str(value))
            option.setdefault("attrs", {})["data-organisation"] = organisation_id or ""
        return option


class AccessionNumberSeriesAdminForm(BaseW3ModelForm):
    TBI_USERNAME = "tbi"
    TBI_ORG_CODE = "tbi"

    count = forms.IntegerField(
        label=_("Count"),
        min_value=1,
        max_value=100,
        required=True,
        help_text=_("Number of accession numbers to generate or total range size."),
        error_messages={
            "max_value": _("You can generate up to 100 accession numbers at a time."),
        },
    )

    class Meta:
        model = AccessionNumberSeries
        fields = [
            "organisation",
            "user",
            "start_from",
            "current_number",
            "is_active",
        ]  # exclude 'count'

    def __init__(self, *args, **kwargs):
        request_user = kwargs.pop("request_user", None)
        self.request_user = request_user
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            # Change view: show disabled count value
            total = (
                self.instance.end_at - self.instance.start_from + 1
                if self.instance.end_at and self.instance.start_from
                else 0
            )
            self.fields["count"].initial = total
            self.fields["count"].disabled = True
        else:
            # Add view: make start_from and current_number readonly and optional
            for field_name in ["start_from", "current_number"]:
                if field_name in self.fields:
                    self.fields[field_name].widget.attrs["readonly"] = True
                    self.fields[field_name].disabled = True
                    self.fields[field_name].required = False
            self.fields["is_active"].initial = True
            self.fields["is_active"].widget = forms.HiddenInput()

        organisation_field = self.fields.get("organisation")
        selected_organisation = None
        if organisation_field:
            organisation_field.required = False
            organisation_field.queryset = Organisation.objects.filter(is_active=True)
            if self.instance.organisation and not organisation_field.initial:
                organisation_field.initial = self.instance.organisation
            resolved_org = _resolve_user_organisation(request_user)
            if (
                resolved_org
                and not organisation_field.initial
                and not (request_user and request_user.is_superuser)
            ):
                organisation_field.initial = resolved_org
            if request_user and not request_user.is_superuser:
                organisation_field.widget = forms.HiddenInput()

            selected_organisation = self._resolve_selected_organisation(organisation_field)

        for field_name in ["collection", "specimen_prefix"]:
            if field_name in self.fields:
                self.fields[field_name].required = False

        metadata = self._widget_metadata()

        # Inject JS data for user field
        if "user" in self.fields:
            user_field = self.fields["user"]
            user_field.label_from_instance = lambda obj: obj.username

            user_org_map = {
                str(user_id): str(org_id)
                for user_id, org_id in UserOrganisation.objects.values_list(
                    "user_id", "organisation_id"
                )
            }

            if request_user is not None:
                if request_user.is_superuser:
                    queryset = User.objects.order_by("username")
                    if selected_organisation:
                        queryset = queryset.filter(
                            organisation_membership__organisation=selected_organisation
                        )
                    user_field.queryset = queryset
                    user_field.widget = UserOrganisationSelect(user_org_map=user_org_map)
                    user_field.widget.choices = user_field.choices
                    user_field.widget.attrs.update(metadata)
                else:
                    user_field.queryset = User.objects.filter(pk=request_user.pk)
                    user_field.initial = request_user
                    user_field.widget = forms.HiddenInput(attrs=metadata)
            else:
                user_field.widget.attrs.update(metadata)

        if request_user is not None and not self.instance.pk:
            next_start = self._next_start_for_user(request_user)

            for field_name in ("start_from", "current_number"):
                if field_name in self.fields:
                    self.fields[field_name].initial = next_start
            self.initial.setdefault("start_from", next_start)
            self.initial.setdefault("current_number", next_start)
            if not getattr(self.instance, "start_from", None):
                self.instance.start_from = next_start
            if not getattr(self.instance, "current_number", None):
                self.instance.current_number = next_start

    @classmethod
    def _next_start_for_pool(cls, *, is_tbi_pool):
        if is_tbi_pool:
            queryset = AccessionNumberSeries.objects.filter(
                organisation__code__iexact=cls.TBI_ORG_CODE
            )
            base = 1_000_000
        else:
            queryset = AccessionNumberSeries.objects.exclude(
                organisation__code__iexact=cls.TBI_ORG_CODE
            )
            base = 1

        latest_series = queryset.order_by("-end_at").first()
        if latest_series and latest_series.end_at:
            return latest_series.end_at + 1
        return base

    @classmethod
    def _is_tbi_user(cls, user):
        organisation = getattr(getattr(user, "organisation_membership", None), "organisation", None)
        if organisation and getattr(organisation, "code", None):
            return organisation.code.strip().lower() == cls.TBI_ORG_CODE
        if not user or not user.username:
            return False
        return user.username.strip().lower() == cls.TBI_USERNAME

    def _next_start_for_user(self, user):
        return self._next_start_for_pool(is_tbi_pool=self._is_tbi_user(user))

    @classmethod
    def _widget_metadata(cls):
        series_map = {
            "tbi": cls._next_start_for_pool(is_tbi_pool=True),
            "shared": cls._next_start_for_pool(is_tbi_pool=False),
        }

        metadata = {"data-series-starts": json.dumps(series_map)}

        dedicated_user_id = (
            User.objects.filter(username__iexact=cls.TBI_USERNAME)
            .values_list("pk", flat=True)
            .first()
        )

        if dedicated_user_id is not None:
            metadata["data-dedicated-user-id"] = str(dedicated_user_id)

        tbi_org_id = (
            Organisation.objects.filter(code__iexact=cls.TBI_ORG_CODE)
            .values_list("pk", flat=True)
            .first()
        )

        if tbi_org_id is not None:
            metadata["data-tbi-org-id"] = str(tbi_org_id)

        return metadata

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get("user")
        organisation = cleaned_data.get("organisation")
        count = cleaned_data.get("count")

        if user:
            resolved_org = organisation or _resolve_user_organisation(user)
            user_org = _resolve_user_organisation(user)

            if user_org and organisation and organisation != user_org:
                self.add_error(
                    "organisation",
                    _("Selected organisation must match the user's organisation."),
                )
                return cleaned_data

            if not resolved_org:
                self.add_error(
                    "organisation",
                    _("An organisation is required for this user."),
                )
                return cleaned_data

            cleaned_data["organisation"] = resolved_org
            self.instance.organisation = resolved_org

        allow_multiple_active = False
        if self.request_user and self.request_user.is_superuser:
            allow_multiple_active = True
        elif user and user.is_superuser:
            allow_multiple_active = True

        self.instance._allow_multiple_active = allow_multiple_active

        if not self.instance.pk and user:
            next_start = self._next_start_for_user(user)
            cleaned_data["start_from"] = next_start
            cleaned_data["current_number"] = next_start

            # Keep instance in sync with the cleaned values so model validation sees them
            self.instance.start_from = next_start
            self.instance.current_number = next_start

        return cleaned_data

    def save(self, commit=True):
        if not self.instance.pk:
            start_from = self.cleaned_data.get("start_from") or self.instance.start_from
            count = self.cleaned_data.get("count")
            if start_from and count:
                self.instance.start_from = start_from
                self.instance.current_number = start_from
                self.instance.end_at = start_from + count - 1
        return super().save(commit=commit)

    def _resolve_selected_organisation(self, organisation_field: forms.ModelChoiceField):
        """Resolve the currently selected organisation from bound data or initial values."""

        org_value = None
        if self.data:
            org_value = self.data.get(self.add_prefix("organisation"))
        if not org_value:
            org_value = organisation_field.initial or getattr(self.instance, "organisation", None)

        if not org_value:
            return None

        if isinstance(org_value, Organisation):
            return org_value

        try:
            return organisation_field.queryset.get(pk=org_value)
        except (Organisation.DoesNotExist, ValueError, TypeError):
            return None


class AccessionRowWidget(s2forms.ModelSelect2Widget):
    search_fields = [
        "accession__collection__description__icontains",
        "accession__specimen_prefix__abbreviation__icontains",
        "accession__specimen_no__icontains",
        "specimen_suffix__icontains",
    ]

    def label_from_instance(self, obj):
        """
        Custom label for dropdown: Show full accession with suffix and collection name
        """
        collection = (
            obj.accession.collection.description
            if obj.accession.collection
            else "Unknown Collection"
        )
        prefix = obj.accession.specimen_prefix.abbreviation
        number = obj.accession.specimen_no
        suffix = obj.specimen_suffix or "-"
        return f"{prefix} {number}{suffix} ({collection})"


class AccessionMediaUploadForm(BaseW3ModelForm):
    class Meta:
        model = Media
        fields = ["media_location", "type", "license", "rights_holder"]
        widgets = {
            "media_location": forms.ClearableFileInput(attrs={"multiple": False}),
        }


class FieldSlipWidget(Select2Widget):
    """Simple Select2 widget that preloads all field slips for selection."""

    def __init__(self, attrs=None, choices=()):
        attrs = attrs or {}
        attrs.setdefault("data-placeholder", "Select a Field Slip")
        attrs.setdefault("data-allow-clear", "true")
        attrs.setdefault("data-minimum-results-for-search", "0")
        attrs.setdefault("class", "template_form_select")
        super().__init__(attrs, choices)


class ElementWidget(s2forms.ModelSelect2Widget):
    search_fields = ["name__icontains"]

    model = Element

    def get_queryset(self):
        return Element.objects.order_by("name")

    def __init__(self, *args, **kwargs):
        attrs = kwargs.pop("attrs", {})
        attrs.setdefault("data-placeholder", "Search for an element")
        attrs.setdefault("data-minimum-input-length", 3)
        attrs.setdefault("data-allow-clear", "true")
        kwargs["attrs"] = attrs
        super().__init__(*args, **kwargs)


class ReferenceWidget(s2forms.ModelSelect2Widget):
    search_fields = [
        "title__icontains",
        "first_author__icontains",
        "citation__icontains",
        "year__icontains",
    ]

    model = Reference
    data_view = "reference-autocomplete"

    def get_queryset(self):
        return Reference.objects.order_by("first_author", "year", "title")

    def __init__(self, *args, **kwargs):
        attrs = kwargs.pop("attrs", {})
        attrs.setdefault(
            "data-placeholder",
            "Search for a reference (type at least 3 characters)",
        )
        attrs.setdefault("data-minimum-input-length", 3)
        attrs.setdefault("data-allow-clear", "true")
        kwargs["attrs"] = attrs
        kwargs.setdefault("data_view", "reference-autocomplete")
        super().__init__(*args, **kwargs)

    def filter_queryset(self, request, term, queryset=None, **dependent_fields):
        term = (term or "").strip()
        if len(term) < 3:
            qs = queryset if queryset is not None else self.get_queryset()
            return qs.none()
        return super().filter_queryset(
            request,
            term,
            queryset=queryset,
            **dependent_fields,
        )


class TaxonWidget(s2forms.ModelSelect2Widget):
    search_fields = [
        "taxon_name__icontains",
        "author_year__icontains",
        "synonyms__taxon_name__icontains",
        "external_id__icontains",
    ]

    def __init__(self, *args, **kwargs):
        attrs = kwargs.setdefault("attrs", {})
        attrs.setdefault("data-placeholder", str(_("Select accepted taxon")))
        attrs.setdefault("data-minimum-input-length", 2)
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        return Taxon.objects.filter(
            status=TaxonStatus.ACCEPTED,
            is_active=True,
        ).order_by("taxon_name")

    def label_from_instance(self, obj):
        base_name = obj.taxon_name or str(obj)
        if obj.author_year:
            return f"{base_name} {obj.author_year}"
        return base_name


class IdentifiedByWidget(s2forms.ModelSelect2TagWidget):
    allow_multiple_selected = False
    model = Person
    search_fields = [
        "first_name__icontains",
        "last_name__icontains",
    ]

    def get_queryset(self):
        return Person.objects.order_by("last_name", "first_name")

    def __init__(self, *args, **kwargs):
        attrs = kwargs.pop("attrs", {})
        attrs.setdefault("data-placeholder", "Select or add a person")
        attrs.setdefault("data-allow-clear", "true")
        attrs.setdefault("data-tags", "true")
        attrs.setdefault("data-token-separators", "[]")
        attrs.setdefault("data-minimum-input-length", 0)
        kwargs["attrs"] = attrs
        super().__init__(*args, **kwargs)

    def value_from_datadict(self, data, files, name):
        self._pending_validation_error = None
        values = super().value_from_datadict(data, files, name)

        if not values:
            return ""

        if isinstance(values, (list, tuple)):
            # Filter out empty placeholders Select2 may submit
            filtered = [value for value in values if value not in (None, "")]
            if not filtered:
                return ""
            value = filtered[0]
        else:
            value = values

        if value in (None, ""):
            return ""

        queryset = self.get_queryset()
        try:
            if queryset.filter(pk=value).exists():
                return str(value)
        except (TypeError, ValueError):
            pass

        try:
            created_pk = self.create_value(value)
        except forms.ValidationError as exc:
            self._pending_validation_error = exc
            return ""

        return str(created_pk)

    def create_value(self, value):
        value = (value or "").strip()
        if not value:
            raise forms.ValidationError("Please enter a name for the identifier.")

        if "," in value:
            last_name, first_name = [part.strip() for part in value.split(",", 1)]
        else:
            parts = value.split()
            if len(parts) < 2:
                raise forms.ValidationError(
                    "Enter both first and last names, e.g. 'Jane Doe'."
                )
            first_name = parts[0]
            last_name = " ".join(parts[1:])

        existing = Person.objects.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
        ).first()

        if existing:
            return existing.pk

        person = Person.objects.create(first_name=first_name, last_name=last_name)
        return person.pk


class AccessionForm(BaseW3ModelForm):
    class Meta:
        model = Accession
        fields = [
            "collection",
            "specimen_prefix",
            "specimen_no",
            "accessioned_by",
            "type_status",
            "comment",
        ]
        widgets = {
            "accessioned_by": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Custom label for Locality field in dropdown
        self.fields["specimen_prefix"].label_from_instance = (
            lambda obj: f"{obj.abbreviation} - {obj.name}"
        )


class AccessionCommentForm(BaseW3ModelForm):
    class Meta:
        model = Comment
        fields = ["subject", "comment", "comment_by"]


class AccessionFieldSlipForm(BaseW3ModelForm):
    fieldslip = forms.ModelChoiceField(
        queryset=FieldSlip.objects.none(),
        widget=FieldSlipWidget(),
        label="Field Slip",
    )

    class Meta:
        model = AccessionFieldSlip
        fields = ["fieldslip", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fieldslip"].queryset = FieldSlip.objects.order_by(
            "field_number", "id"
        )
        self.fields["fieldslip"].empty_label = "Select a Field Slip"
        self.fields["fieldslip"].widget.choices = self.fields["fieldslip"].choices


class FieldSlipMergeForm(BaseW3Form):
    target = forms.ModelChoiceField(
        queryset=FieldSlip.objects.none(),
        label=_("Target field slip"),
    )
    source = forms.ModelChoiceField(
        queryset=FieldSlip.objects.none(),
        label=_("Source field slip"),
    )

    def __init__(self, *args, accession: Accession, **kwargs):
        self.accession = accession
        super().__init__(*args, **kwargs)
        fieldslips = (
            FieldSlip.objects.filter(accession_links__accession=accession)
            .distinct()
            .order_by("field_number", "id")
        )
        self.fields["target"].queryset = fieldslips
        self.fields["source"].queryset = fieldslips

    def clean(self):
        cleaned_data = super().clean()
        target = cleaned_data.get("target")
        source = cleaned_data.get("source")

        if target and source and target == source:
            self.add_error("source", _("Select two different field slips to merge."))

        if not self.accession.fieldslip_links.filter(fieldslip=target).exists():
            self.add_error("target", _("Select a field slip linked to this accession."))

        if not self.accession.fieldslip_links.filter(fieldslip=source).exists():
            self.add_error("source", _("Select a field slip linked to this accession."))

        return cleaned_data


class AccessionReferenceMergeSelectionForm(BaseW3Form):
    """Select accession reference candidates and a target for merge."""

    selected_ids = forms.MultipleChoiceField(
        choices=(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Select references to merge"),
    )
    target = forms.ChoiceField(
        choices=(),
        widget=forms.RadioSelect,
        label=_("Choose the target reference"),
    )

    def __init__(self, *args, accession: Accession, **kwargs) -> None:
        self.accession = accession
        self._choices: list[tuple[str, str]] = []
        super().__init__(*args, **kwargs)
        references = (
            accession.accessionreference_set.select_related("reference")
            .order_by("reference__year", "reference__first_author", "pk")
        )

        for ref in references:
            label_parts = [
                ref.reference.year if ref.reference else "",
                ref.reference.first_author if ref.reference else "",
                ref.reference.title if ref.reference else "",
                _("Page %(page)s") % {"page": ref.page} if ref.page else "",
            ]
            label = " • ".join(part for part in label_parts if part)
            if not label:
                label = _("Accession reference %(pk)s") % {"pk": ref.pk}
            self._choices.append((str(ref.pk), label))

        self.fields["selected_ids"].choices = self._choices
        self.fields["target"].choices = self._choices
        if not self.fields["target"].initial and self._choices:
            self.fields["target"].initial = self._choices[0][0]

    def clean(self):
        cleaned = super().clean()
        selected_ids = cleaned.get("selected_ids") or []
        target = cleaned.get("target")

        valid_ids = {choice[0] for choice in self._choices}
        ordered_selected: list[str] = []
        for raw_id in self.data.getlist("selected_ids"):
            if raw_id in valid_ids and raw_id not in ordered_selected:
                ordered_selected.append(raw_id)
        if ordered_selected:
            cleaned["selected_ids"] = ordered_selected

        if not selected_ids:
            self.add_error("selected_ids", _("Select at least two references to merge."))
            return cleaned
        if len(selected_ids) < 2:
            self.add_error("selected_ids", _("Select at least two references to merge."))

        invalid = [value for value in selected_ids if value not in valid_ids]
        if invalid:
            self.add_error(
                "selected_ids",
                _("One or more selected references are not linked to this accession."),
            )

        if target and target not in valid_ids:
            self.add_error("target", _("Choose a valid target reference."))
        if target and target not in selected_ids:
            self.add_error(
                "target",
                _("The target reference must be included in the merge selection."),
            )

        return cleaned


class AccessionReferenceFieldSelectionForm(FieldSelectionForm):
    """FIELD_SELECTION merge form for :class:`AccessionReference` candidates."""

    merge_field_names = ("reference", "page")

    def __init__(
        self,
        *,
        candidates: Iterable[FieldSelectionCandidate | AccessionReference],
        data: dict[str, object] | None = None,
        initial: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            model=AccessionReference,
            merge_fields=self.get_mergeable_fields(),
            candidates=candidates,
            data=data,
            initial=initial,
        )

    @classmethod
    def get_mergeable_fields(cls) -> tuple[models.Field, ...]:
        fields: list[models.Field] = []
        for field_name in cls.merge_field_names:
            try:
                fields.append(AccessionReference._meta.get_field(field_name))
            except Exception:
                continue
        return tuple(fields)

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()

        if len(self.candidates) < 2:
            raise forms.ValidationError(
                _("Select at least two accession references to merge."),
            )

        accession_ids = {
            candidate.instance.accession_id for candidate in self.candidates
        }
        if len(accession_ids) > 1:
            raise forms.ValidationError(
                _("Accession references must belong to the same accession."),
            )

        return cleaned_data


class AccessionElementMergeSelectionForm(BaseW3Form):
    """Select specimen elements (NatureOfSpecimen) to merge for an accession row."""

    selected_ids = forms.MultipleChoiceField(
        choices=(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Select elements to merge"),
    )
    target = forms.ChoiceField(
        choices=(),
        widget=forms.RadioSelect,
        label=_("Choose the target element"),
    )

    def __init__(self, *args, accession_row: AccessionRow, **kwargs) -> None:
        self.accession_row = accession_row
        self._choices: list[tuple[str, str]] = []
        super().__init__(*args, **kwargs)
        specimens = (
            accession_row.natureofspecimen_set.select_related("element")
            .order_by("element__name", "pk")
        )
        for specimen in specimens:
            label_parts = [
                specimen.element.name if specimen.element else _("Unknown element"),
                specimen.side or "",
                specimen.verbatim_element or "",
            ]
            label = " • ".join(part for part in label_parts if part)
            self._choices.append((str(specimen.pk), label))

        self.fields["selected_ids"].choices = self._choices
        self.fields["target"].choices = self._choices
        if not self.fields["target"].initial and self._choices:
            self.fields["target"].initial = self._choices[0][0]

    def clean(self):
        cleaned = super().clean()
        selected_ids = cleaned.get("selected_ids") or []
        target = cleaned.get("target")
        valid_ids = {choice[0] for choice in self._choices}

        ordered_selected: list[str] = []
        for raw_id in self.data.getlist("selected_ids"):
            if raw_id in valid_ids and raw_id not in ordered_selected:
                ordered_selected.append(raw_id)
        if ordered_selected:
            cleaned["selected_ids"] = ordered_selected

        if not selected_ids or len(selected_ids) < 2:
            self.add_error("selected_ids", _("Select at least two elements to merge."))

        invalid = [value for value in selected_ids if value not in valid_ids]
        if invalid:
            self.add_error(
                "selected_ids",
                _("One or more selected elements are not linked to this specimen."),
            )

        if target and target not in valid_ids:
            self.add_error("target", _("Choose a valid target element."))
        if target and target not in selected_ids:
            self.add_error(
                "target",
                _("The target element must be included in the merge selection."),
            )

        return cleaned


class AccessionElementFieldSelectionForm(FieldSelectionForm):
    """FIELD_SELECTION merge form for :class:`NatureOfSpecimen` candidates."""

    merge_field_names = (
        "element",
        "side",
        "condition",
        "verbatim_element",
        "portion",
        "fragments",
    )

    def __init__(
        self,
        *,
        candidates: Iterable[FieldSelectionCandidate | NatureOfSpecimen],
        data: dict[str, object] | None = None,
        initial: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            model=NatureOfSpecimen,
            merge_fields=self.get_mergeable_fields(),
            candidates=candidates,
            data=data,
            initial=initial,
        )

    @classmethod
    def get_mergeable_fields(cls) -> tuple[models.Field, ...]:
        fields: list[models.Field] = []
        for field_name in cls.merge_field_names:
            try:
                fields.append(NatureOfSpecimen._meta.get_field(field_name))
            except Exception:
                continue
        return tuple(fields)

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()

        if len(self.candidates) < 2:
            raise forms.ValidationError(
                _("Select at least two elements to merge."),
            )

        accession_row_ids = {candidate.instance.accession_row_id for candidate in self.candidates}
        if len(accession_row_ids) > 1:
            raise forms.ValidationError(
                _("Elements must belong to the same accession row."),
            )

        return cleaned_data

    def build_selected_fields(self) -> dict[str, object]:
        """Return selected fields mirroring element merge semantics."""

        selected: dict[str, object] = {}
        for field in self.merge_fields:
            field_name = field.name
            choice = self.cleaned_data.get(self.selection_field_name(field_name))
            if not choice:
                continue

            candidate = self._candidate_map.get(choice)
            if not candidate:
                continue

            if candidate.role == "target":
                selected[field_name] = "target"
                continue

            value = field.value_from_object(candidate.instance)
            selected[field_name] = value

        return selected


class AccessionGeologyForm(BaseW3ModelForm):
    class Meta:
        model = SpecimenGeology
        fields = ["earliest_geological_context", "latest_geological_context"]


class AccessionReferenceForm(BaseW3ModelForm):
    class Meta:
        model = AccessionReference
        fields = ["reference", "page"]
        help_texts = {
            "page": _("Use numeric pages, ranges, or figure labels (for example: \"12\", \"12-14\", or \"Fig. 3\".)"),
        }
        widgets = {
            "reference": ReferenceWidget,
        }


class AccessionReferenceForm2(BaseW3ModelForm):
    reference = forms.ModelChoiceField(
        queryset=Reference.objects.all(),
        widget=ModelSelect2Widget(
            model=Reference,
            search_fields=["title__icontains"],  # Allows searching by title
            attrs={"data-placeholder": "Select References..."},
        ),
    )

    class Meta:
        model = AccessionReference
        fields = ["reference", "page"]
        help_texts = {
            "page": _("Use numeric pages, ranges, or figure labels (for example: \"12\", \"12-14\", or \"Fig. 3\".)"),
        }


class FieldSlipForm(BaseW3ModelForm):
    collection_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )

    class Meta:
        model = FieldSlip
        fields = [
            "field_number",
            "discoverer",
            "collector",
            "collection_date",
            "verbatim_locality",
            "verbatim_taxon",
            "verbatim_element",
            "verbatim_horizon",
            "aerial_photo",
            "verbatim_latitude",
            "verbatim_longitude",
            "verbatim_SRS",
            "verbatim_coordinate_system",
            "verbatim_elevation",
        ]


class ReferenceForm(BaseW3ModelForm):
    class Meta:
        model = Reference
        fields = [
            "title",
            "first_author",
            "year",
            "journal",
            "volume",
            "issue",
            "pages",
            "doi",
            "citation",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "template_form_input"}),
            "first_author": forms.TextInput(attrs={"class": "template_form_input"}),
            "year": forms.TextInput(
                attrs={"class": "template_form_input", "type": "year"}
            ),
            "journal": forms.DateInput(attrs={"class": "template_form_input"}),
            "volume": forms.TextInput(attrs={"class": "template_form_input"}),
            "issue": forms.TextInput(attrs={"class": "template_form_input"}),
            "pages": forms.TextInput(attrs={"class": "template_form_input"}),
            "doi": forms.TextInput(attrs={"class": "template_form_input"}),
            "citation": forms.TextInput(attrs={"class": "template_form_input"}),
        }


class LocalityForm(BaseW3ModelForm):
    geological_times = forms.MultipleChoiceField(
        label=_("Geological time"),
        required=False,
        choices=Locality.GeologicalTime.choices,
        widget=forms.SelectMultiple(attrs={"class": "template_form_select"}),
        help_text=_("Select relevant geological times for this locality."),
    )

    class Meta:
        model = Locality
        fields = ["abbreviation", "name", "geological_times"]
        widgets = {
            "abbreviation": forms.TextInput(attrs={"class": "template_form_input"}),
            "name": forms.TextInput(attrs={"class": "template_form_input"}),
        }


class PlaceForm(BaseW3ModelForm):
    class Meta:
        model = Place
        fields = [
            "locality",
            "name",
            "place_type",
            "related_place",
            "relation_type",
            "description",
            "comment",
        ]
        widgets = {
            "locality": forms.Select(attrs={"class": "template_form_select"}),
            "name": forms.TextInput(attrs={"class": "template_form_input"}),
            "place_type": forms.Select(attrs={"class": "template_form_select"}),
            "related_place": forms.Select(attrs={"class": "template_form_select"}),
            "relation_type": forms.Select(attrs={"class": "template_form_select"}),
            "description": forms.Textarea(attrs={"class": "template_form_textarea"}),
            "comment": forms.Textarea(attrs={"class": "template_form_textarea"}),
        }


class MediaUploadForm(BaseW3ModelForm):
    class Meta:
        model = Media
        fields = ["media_location", "type", "license", "rights_holder"]


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.Field):
    widget = MultiFileInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, value):
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            return [item for item in value if item]
        return [value]


class ScanUploadForm(BaseW3Form):
    files = MultiFileField(label="Scan files")

    def __init__(self, *args, **kwargs):
        self.max_upload_bytes = kwargs.pop(
            "max_upload_bytes", settings.SCAN_UPLOAD_MAX_BYTES
        )
        super().__init__(*args, **kwargs)

    def clean_files(self):
        uploaded_files = self.cleaned_data.get("files", [])
        if not uploaded_files:
            raise forms.ValidationError(
                "No file was submitted. Check the encoding type on the form."
            )

        limit_display = filesizeformat(self.max_upload_bytes)
        errors = []

        for uploaded in uploaded_files:
            if uploaded.size > self.max_upload_bytes:
                errors.append(
                    f"{uploaded.name} is {filesizeformat(uploaded.size)}, which exceeds the {limit_display} limit per file."
                )

        if errors:
            raise forms.ValidationError(errors)

        return uploaded_files


class AddAccessionRowForm(BaseW3ModelForm):
    specimen_suffix = forms.ChoiceField(choices=[], required=False)
    accession = forms.ModelChoiceField(
        queryset=Accession.objects.all(),
        widget=forms.HiddenInput(),  # Ensure it's hidden in the form
    )

    class Meta:
        model = AccessionRow
        fields = ["accession", "storage", "specimen_suffix", "status"]

    def __init__(self, *args, **kwargs):
        """Dynamically populate specimen_suffix choices based on the accession"""
        accession = kwargs.pop("accession", None)  # Get accession from kwargs

        super().__init__(*args, **kwargs)

        self.fields["storage"].queryset = Storage.objects.order_by("area")
        self.fields["storage"].required = False
        self.fields["status"].required = False

        if accession:
            self.fields["accession"].initial = accession  # Set initial accession value
            self.fields["specimen_suffix"].choices = (
                self.get_available_specimen_suffixes(accession)
            )
        else:
            self.fields["specimen_suffix"].choices = [("-", "-")]

        if not self.fields["specimen_suffix"].initial:
            self.fields["specimen_suffix"].initial = "-"

    def get_available_specimen_suffixes(self, accession):
        """Returns a list of available specimen_suffix options"""
        taken_suffixes = set(
            AccessionRow.objects.filter(accession=accession).values_list(
                "specimen_suffix", flat=True
            )
        )
        all_valid_suffixes = (
            AccessionRow().generate_valid_suffixes()
        )  # Get valid suffixes
        available_suffixes = [("-", "-")]  # Default choice

        for suffix in all_valid_suffixes:
            if suffix not in taken_suffixes:
                available_suffixes.append((suffix, suffix))

        return available_suffixes

    def clean_specimen_suffix(self):
        suffix = self.cleaned_data.get("specimen_suffix")
        return suffix or "-"


class AccessionRowUpdateForm(BaseW3ModelForm):
    specimen_suffix = forms.ChoiceField(choices=[], required=False)

    class Meta:
        model = AccessionRow
        fields = ["storage", "specimen_suffix", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accession_row = self.instance
        accession = getattr(accession_row, "accession", None)

        if accession:
            taken_suffixes = set(
                AccessionRow.objects.filter(accession=accession)
                .exclude(pk=accession_row.pk)
                .values_list("specimen_suffix", flat=True)
            )
            valid_suffixes = accession_row.generate_valid_suffixes()
            choices = [("-", "-")]
            for suffix in valid_suffixes:
                if (
                    suffix not in taken_suffixes
                    or suffix == accession_row.specimen_suffix
                ):
                    choices.append((suffix, suffix))
            if (
                accession_row.specimen_suffix
                and accession_row.specimen_suffix not in dict(choices)
            ):
                choices.append(
                    (accession_row.specimen_suffix, accession_row.specimen_suffix)
                )
            self.fields["specimen_suffix"].choices = choices
            self.fields["specimen_suffix"].initial = (
                accession_row.specimen_suffix or "-"
            )

        self.fields["storage"].queryset = Storage.objects.order_by("area")
        self.fields["storage"].required = False

    def clean_specimen_suffix(self):
        suffix = self.cleaned_data.get("specimen_suffix")
        return suffix or "-"


class NatureOfSpecimenForm(BaseW3ModelForm):
    element = forms.ModelChoiceField(
        queryset=Element.objects.order_by("name"),
        widget=ElementWidget(),
    )

    class Meta:
        model = NatureOfSpecimen
        fields = [
            "element",
            "side",
            "condition",
            "verbatim_element",
            "portion",
            "fragments",
        ]


class AddSpecimenForm(BaseW3ModelForm):
    accession_row = forms.ModelChoiceField(
        queryset=AccessionRow.objects.all(),
        widget=forms.HiddenInput(),  # Ensure it's hidden in the form
    )

    class Meta:
        model = NatureOfSpecimen
        fields = [
            "element",
            "side",
            "condition",
            "verbatim_element",
            "portion",
            "fragments",
        ]

    def __init__(self, *args, **kwargs):
        accession_row = kwargs.pop("accession_row", None)  # Get accession from kwargs

        super().__init__(*args, **kwargs)

        if accession_row:
            self.fields["accession_row"].initial = (
                accession_row  # Set initial accession_row value
            )


class AccessionRowIdentificationForm(BaseW3ModelForm):
    taxon_record_display = forms.CharField(
        label=_("Taxon record"),
        required=False,
        disabled=True,
        help_text=_("Automatically linked when the taxon matches a controlled record."),
    )
    reference = forms.ModelChoiceField(
        queryset=Reference.objects.order_by("first_author", "year", "title"),
        required=False,
        widget=ReferenceWidget(),
    )

    class Meta:
        model = Identification
        fields = [
            "identified_by",
            "taxon_verbatim",
            "reference",
            "date_identified",
            "identification_qualifier",
            "verbatim_identification",
            "identification_remarks",
        ]
        labels = {
            "identification_qualifier": "Taxon Qualifier",
            "taxon_verbatim": "Taxon (free text)",
            "verbatim_identification": "Taxon Verbatim",
            "identification_remarks": "Remarks",
        }
        widgets = {
            "identified_by": IdentifiedByWidget(),
            "date_identified": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["identified_by"].queryset = Person.objects.order_by(
            "last_name", "first_name"
        )
        taxon_record = getattr(self.instance, "taxon_record", None)
        self.fields["taxon_record_display"].initial = (
            taxon_record.taxon_name if taxon_record else ""
        )
        self.fields["taxon_record_display"].widget.attrs["readonly"] = True
        self.order_fields(
            [
                "identified_by",
                "taxon_verbatim",
                "taxon_record_display",
                "reference",
                "date_identified",
                "identification_qualifier",
                "verbatim_identification",
                "identification_remarks",
            ]
        )

    def clean_identified_by(self):
        widget = self.fields["identified_by"].widget
        pending_error = getattr(widget, "_pending_validation_error", None)
        if pending_error is not None:
            widget._pending_validation_error = None
            raise pending_error

        return self.cleaned_data.get("identified_by")

    def clean_taxon_verbatim(self):
        return coerce_stripped(self.cleaned_data.get("taxon_verbatim"))

    def clean(self):
        cleaned_data = super().clean()
        taxon_verbatim = cleaned_data.get("taxon_verbatim")

        if not taxon_verbatim:
            self.add_error(
                "taxon_verbatim",
                _("Enter the lowest level of taxonomy for this identification."),
            )
        return cleaned_data


class AccessionRowSpecimenForm(BaseW3ModelForm):
    element = forms.ModelChoiceField(
        queryset=Element.objects.order_by("name"),
        widget=ElementWidget(),
    )

    class Meta:
        model = NatureOfSpecimen
        fields = [
            "verbatim_element",
            "element",
            "side",
            "portion",
            "fragments",
            "condition",
        ]


class PreparationForm(BaseW3ModelForm):
    """Form for creating/updating preparation records."""

    class Meta:
        model = Preparation
        fields = [
            "accession_row",
            "preparation_type",
            "reason",
            "preparator",
            "curator",
            "status",
            "started_on",
            "completed_on",
            "original_storage",
            "temporary_storage",
            "condition_before",
            "condition_after",
            "preparation_method",
            "chemicals_used",
            "materials_used",
            "notes",
        ]
        widgets = {
            "started_on": forms.DateInput(attrs={"type": "date"}),
            "completed_on": forms.DateInput(attrs={"type": "date"}),
            "accession_row": AccessionRowWidget,
        }


class PreparationApprovalForm(BaseW3ModelForm):
    """Form for curators to approve or decline a preparation."""

    class Meta:
        model = Preparation
        fields = ["approval_status", "curator_comments"]


class PreparationMediaUploadForm(BaseW3Form):
    media_files = forms.FileField(
        widget=forms.FileInput(attrs={"multiple": False}), label="Upload media files"
    )
    context = forms.ChoiceField(
        choices=[
            ("before", "Before Preparation"),
            ("after", "After Preparation"),
            ("in_progress", "In Progress"),
            ("other", "Other"),
        ],
        initial="before",
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class SpecimenCompositeForm(BaseW3Form):
    storage = forms.ModelChoiceField(
        queryset=AccessionRow._meta.get_field("storage").related_model.objects.all(),
        required=True,
        empty_label="Select a storage location",
    )

    element = forms.ModelChoiceField(queryset=Element.objects.all(), required=True)
    side = forms.CharField(max_length=50, required=False)
    condition = forms.CharField(max_length=255, required=False)
    fragments = forms.IntegerField(min_value=0, required=False)
    taxon = forms.CharField(max_length=255, required=False)
    identified_by = forms.ModelChoiceField(
        queryset=Person.objects.all(), required=False
    )


class DrawerRegisterForm(BaseW3ModelForm):
    class Meta:
        model = DrawerRegister
        fields = [
            "code",
            "description",
            "localities",
            "taxa",
            "estimated_documents",
            "scanning_status",
            "scanning_users",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow both legacy rank data and new accepted taxonomy schema without
        # mixing distinct/non-distinct querysets that trigger TypeError on MySQL.
        accepted_orders_q = (
            Q(taxon_rank=TaxonRank.ORDER) | Q(taxon_rank__iexact=TaxonRank.ORDER)
        ) & Q(status=TaxonStatus.ACCEPTED, is_active=True)

        filter_q = accepted_orders_q
        if self.instance.pk:
            selected_ids = list(self.instance.taxa.values_list("pk", flat=True))
            if selected_ids:
                filter_q = filter_q | Q(pk__in=selected_ids)

        queryset = (
            Taxon.objects.filter(filter_q)
            .distinct()
            .order_by("taxon_name", "pk")
        )
        self.fields["taxa"].queryset = queryset

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("scanning_status")
        users = cleaned_data.get("scanning_users")
        if status == DrawerRegister.ScanningStatus.IN_PROGRESS and not users:
            raise forms.ValidationError(
                "Scanning user is required when status is In progress."
            )
        return cleaned_data


class StorageForm(BaseW3ModelForm):
    class Meta:
        model = Storage
        fields = ["area", "parent_area"]
        widgets = {
            "area": forms.TextInput(attrs={"class": "w3-input"}),
            "parent_area": forms.Select(attrs={"class": "w3-select"}),
        }


MANUAL_IMPORT_PERMISSION_CODENAME = "can_import_manual_qc"
_MANUAL_IMPORT_PERMISSION_NAME = _("Can import manual QC data")

_SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _column_index_from_reference(reference: str | None) -> int:
    if not reference:
        return 0
    letters: List[str] = []
    for char in reference:
        if char.isalpha():
            letters.append(char.upper())
        else:
            break
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def _read_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        with zf.open("xl/sharedStrings.xml") as handle:
            tree = ElementTree.parse(handle)
    except KeyError:
        return []
    root = tree.getroot()
    shared_strings: List[str] = []
    for si in root.iter(f"{_SPREADSHEET_NS}si"):
        pieces: List[str] = []
        for text_node in si.iter(f"{_SPREADSHEET_NS}t"):
            if text_node.text:
                pieces.append(text_node.text)
        shared_strings.append("".join(pieces))
    return shared_strings


def _resolve_first_sheet_path(zf: zipfile.ZipFile) -> str:
    with zf.open("xl/workbook.xml") as handle:
        workbook_tree = ElementTree.parse(handle)
    root = workbook_tree.getroot()
    sheet = root.find(f"{_SPREADSHEET_NS}sheets/{_SPREADSHEET_NS}sheet")
    if sheet is None:
        raise ValueError(str(_("The Excel workbook does not contain any worksheets.")))
    rel_id = sheet.attrib.get(f"{_REL_NS}id")
    if not rel_id:
        return "xl/worksheets/sheet1.xml"
    with zf.open("xl/_rels/workbook.xml.rels") as handle:
        rels_tree = ElementTree.parse(handle)
    rel_root = rels_tree.getroot()
    for rel in rel_root.findall(f"{_PKG_REL_NS}Relationship"):
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib.get("Target", "")
            if not target:
                break
            joined = posixpath.normpath(posixpath.join("xl", target))
            return joined.lstrip("/")
    return "xl/worksheets/sheet1.xml"


def _read_cell_value(cell, shared_strings: List[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{_SPREADSHEET_NS}is")
        if inline is not None:
            return "".join(part for part in inline.itertext())
        return ""
    value = cell.findtext(f"{_SPREADSHEET_NS}v", default="")
    if cell_type == "s":
        try:
            index = int(value)
        except (TypeError, ValueError):
            return ""
        if 0 <= index < len(shared_strings):
            return shared_strings[index]
        return ""
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE"
    if cell_type == "str":
        if value:
            return value
        text_node = cell.find(f"{_SPREADSHEET_NS}t")
        if text_node is not None and text_node.text:
            return text_node.text
        return ""
    return value


def _extract_sheet_rows(
    zf: zipfile.ZipFile, sheet_path: str, shared_strings: List[str]
) -> List[List[str]]:
    with zf.open(sheet_path) as handle:
        sheet_tree = ElementTree.parse(handle)
    root = sheet_tree.getroot()
    rows: List[List[str]] = []
    for row in root.findall(f"{_SPREADSHEET_NS}sheetData/{_SPREADSHEET_NS}row"):
        values: List[str] = []
        for cell in row.findall(f"{_SPREADSHEET_NS}c"):
            reference = cell.attrib.get("r")
            column_index = _column_index_from_reference(reference)
            while len(values) <= column_index:
                values.append("")
            values[column_index] = _read_cell_value(cell, shared_strings) or ""
        rows.append(values)
    return rows


def _trim_empty_columns(rows: List[List[str]]) -> List[List[str]]:
    if not rows:
        return rows
    max_index = -1
    for row in rows:
        for index, value in enumerate(row):
            if str(value).strip():
                if index > max_index:
                    max_index = index
    if max_index == -1:
        return []
    trimmed: List[List[str]] = []
    for row in rows:
        trimmed.append(row[: max_index + 1])
    return trimmed


def _load_xlsx_dataset(data: bytes) -> Dataset:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            shared_strings = _read_shared_strings(zf)
            sheet_path = _resolve_first_sheet_path(zf)
            rows = _extract_sheet_rows(zf, sheet_path, shared_strings)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValueError(
            str(_("The uploaded Excel file is not a valid .xlsx workbook."))
        ) from exc

    rows = _trim_empty_columns(rows)
    if not rows:
        return Dataset()

    dataset = Dataset()
    headers = [str(value).strip() for value in rows[0]]
    dataset.headers = headers
    for data_row in rows[1:]:
        normalized = [str(value) if value is not None else "" for value in data_row]
        if len(normalized) < len(headers):
            normalized.extend([""] * (len(headers) - len(normalized)))
        elif len(normalized) > len(headers):
            normalized = normalized[: len(headers)]
        dataset.append(normalized)
    return dataset


@dataclass(slots=True)
class ManualImportFailure:
    row_number: int
    identifier: str | None
    message: str


@dataclass
class ManualImportSummary:
    total_rows: int
    success_count: int = 0
    created_count: int = 0
    failures: List[ManualImportFailure] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.failures)

    def build_error_report(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["row_number", "identifier", "message"])
        for failure in self.failures:
            writer.writerow([failure.row_number, failure.identifier or "", failure.message])
        return output.getvalue()


def ensure_manual_qc_permission() -> Permission:
    """Ensure the custom manual import permission exists and return it."""

    content_type = ContentType.objects.get_for_model(Media)
    permission, created = Permission.objects.get_or_create(
        codename=MANUAL_IMPORT_PERMISSION_CODENAME,
        content_type=content_type,
        defaults={"name": str(_MANUAL_IMPORT_PERMISSION_NAME)},
    )
    desired_name = str(_MANUAL_IMPORT_PERMISSION_NAME)
    if not created and permission.name != desired_name:
        permission.name = desired_name
        permission.save(update_fields=["name"])
    return permission


def load_manual_qc_dataset(file_obj) -> Dataset:
    """Load a tabular dataset from an uploaded manual QC file."""

    data = file_obj.read()
    if not data:
        raise ValueError(str(_("The uploaded file is empty.")))

    suffix = Path(getattr(file_obj, "name", "")).suffix.lower()
    format_hint = {
        ".csv": "csv",
        ".tsv": "tsv",
        ".xlsx": "xlsx",
        ".xls": "xls",
    }.get(suffix)

    dataset: Dataset

    try:
        if format_hint in {"csv", "tsv"}:
            dataset = Dataset()
            dataset.load(data.decode("utf-8-sig"), format=format_hint)
        elif format_hint == "xlsx":
            dataset = _load_xlsx_dataset(data)
        elif format_hint == "xls":
            raise ValueError(
                str(
                    _(
                        "Legacy .xls files are not supported. Save the workbook as .xlsx or CSV."
                    )
                )
            )
        else:
            try:
                dataset = Dataset()
                dataset.load(data.decode("utf-8-sig"), format="csv")
            except UnicodeDecodeError:
                dataset = _load_xlsx_dataset(data)
    except Exception as exc:  # pragma: no cover - defensive guard around tablib
        raise ValueError(
            str(_("The uploaded file could not be parsed. Upload a CSV or Excel file."))
        ) from exc
    finally:
        file_obj.seek(0)

    if not dataset.headers:
        raise ValueError(str(_("The uploaded file must include a header row.")))

    return dataset


def dataset_to_rows(dataset: Dataset) -> List[dict[str, Any]]:
    """Convert a dataset into normalized row dictionaries."""

    normalized_headers = [
        str(header).strip().lower()
        for header in dataset.headers
        if header is not None and str(header).strip()
    ]

    if "id" not in normalized_headers:
        raise ValueError(str(_("The header row must include an 'id' column.")))

    rows: List[dict[str, Any]] = []
    for raw_row in dataset.dict:
        normalized_row: dict[str, Any] = {}
        for key, value in raw_row.items():
            normalized_key = str(key).strip().lower()
            if normalized_key:
                normalized_row[normalized_key] = value
        rows.append(normalized_row)

    if not rows:
        raise ValueError(str(_("The uploaded file does not contain any data rows.")))

    return rows


def run_manual_qc_import(
    rows: Iterable[dict[str, Any]],
    *,
    queryset=None,
    default_created_by: str | None = None,
) -> ManualImportSummary:
    """Execute manual QC import rows and capture a summary."""

    prepared_rows: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        if default_created_by and not coerce_stripped(row.get("created_by")):
            row["created_by"] = default_created_by
        prepared_rows.append(row)

    summary = ManualImportSummary(total_rows=len(prepared_rows))

    if not prepared_rows:
        return summary

    if queryset is None:
        queryset = Media.objects.all()

    position = 0
    row_number = 2

    while position < len(prepared_rows):
        current_row = prepared_rows[position]
        context = parse_accession_number(current_row.get("accession_number"))
        key = None
        if context.specimen_prefix and context.specimen_number is not None:
            key = (context.specimen_prefix, context.specimen_number)

        group: list[dict[str, Any]] = [current_row]
        position += 1

        while position < len(prepared_rows):
            candidate = prepared_rows[position]
            candidate_context = parse_accession_number(candidate.get("accession_number"))
            candidate_key = None
            if candidate_context.specimen_prefix and candidate_context.specimen_number is not None:
                candidate_key = (
                    candidate_context.specimen_prefix,
                    candidate_context.specimen_number,
                )
            if key and candidate_key == key:
                group.append(candidate)
                position += 1
            else:
                break

        identifiers = [coerce_stripped(item.get("id")) for item in group]

        try:
            result = import_manual_row(group, queryset=queryset)
        except ManualImportError as exc:
            for offset, identifier in enumerate(identifiers):
                summary.failures.append(
                    ManualImportFailure(
                        row_number=row_number + offset,
                        identifier=identifier,
                        message=str(exc),
                    )
                )
            row_number += len(group)
            continue
        except Exception as exc:  # pragma: no cover - unexpected errors bubbled to caller
            for offset, identifier in enumerate(identifiers):
                summary.failures.append(
                    ManualImportFailure(
                        row_number=row_number + offset,
                        identifier=identifier,
                        message=str(exc),
                    )
                )
            row_number += len(group)
            continue

        summary.success_count += len(group)
        if isinstance(result, dict):
            created_records = result.get("created")
            if isinstance(created_records, list):
                summary.created_count += len(created_records)

        row_number += len(group)

    return summary


class ManualQCImportForm(BaseW3Form):
    dataset_file = forms.FileField(
        label=_("Manual QC spreadsheet"),
        help_text=_("Upload a CSV or Excel file containing the manually validated QC rows."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rows: List[dict[str, Any]] = []

    def clean_dataset_file(self):
        uploaded = self.cleaned_data["dataset_file"]
        try:
            dataset = load_manual_qc_dataset(uploaded)
            rows = dataset_to_rows(dataset)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

        self._rows = rows
        return uploaded

    @property
    def rows(self) -> List[dict[str, Any]]:
        return self._rows

    def execute_import(self, user) -> ManualImportSummary:
        if not self._rows:
            raise ValueError("ManualQCImportForm must be validated before executing the import.")

        queryset = Media.objects.all()
        default_created_by = None
        if getattr(user, "is_authenticated", False):
            default_created_by = user.get_username()

        return run_manual_qc_import(
            self._rows,
            queryset=queryset,
            default_created_by=default_created_by,
        )
