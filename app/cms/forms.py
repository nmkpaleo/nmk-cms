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
from django.contrib.auth.models import User
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
    Place,
    Media,
    NatureOfSpecimen,
    Person,
    Preparation,
    Reference,
    SpecimenGeology,
    DrawerRegister,
    Storage,
    Taxon,
    TaxonRank,
    TaxonStatus,
)

import json

from cms.manual_import import ManualImportError, import_manual_row
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


class AccessionNumberSeriesAdminForm(BaseW3ModelForm):
    TBI_USERNAME = "tbi"

    count = forms.IntegerField(
        label="Count",
        min_value=1,
        required=True,
        help_text="Number of accession numbers to generate.",
    )

    class Meta:
        model = AccessionNumberSeries
        fields = [
            "user",
            "start_from",
            "current_number",
            "is_active",
        ]  # exclude 'count'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Always add count to the form manually
        self.fields["count"] = forms.IntegerField(
            label="Count",
            min_value=1,
            required=True,
            help_text="Number of accession numbers to generate or total range size.",
        )

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
                    self.fields[field_name].required = False
            self.fields["is_active"].initial = True
            self.fields["is_active"].widget = forms.HiddenInput()

        # Inject JS data for user field
        if "user" in self.fields:
            self.fields["user"].widget.attrs.update(self._widget_metadata())
            self.fields["user"].label_from_instance = (
                lambda obj: obj.username
            )  # ensure username shown

    @classmethod
    def _next_start_for_pool(cls, *, is_tbi_pool):
        if is_tbi_pool:
            queryset = AccessionNumberSeries.objects.filter(
                user__username__iexact=cls.TBI_USERNAME
            )
            base = 1_000_000
        else:
            queryset = AccessionNumberSeries.objects.exclude(
                user__username__iexact=cls.TBI_USERNAME
            )
            base = 1

        latest_series = queryset.order_by("-end_at").first()
        if latest_series and latest_series.end_at:
            return latest_series.end_at + 1
        return base

    @classmethod
    def _is_tbi_user(cls, user):
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

        return metadata

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get("user")

        if not self.instance.pk and user:
            # Ensure unique active series per user
            if AccessionNumberSeries.objects.filter(user=user, is_active=True).exists():
                self.add_error(
                    "user", "This user already has an active accession number series."
                )

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


class AccessionGeologyForm(BaseW3ModelForm):
    class Meta:
        model = SpecimenGeology
        fields = ["earliest_geological_context", "latest_geological_context"]


class AccessionReferenceForm(BaseW3ModelForm):
    class Meta:
        model = AccessionReference
        fields = ["reference", "page"]
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
    class Meta:
        model = Locality
        fields = ["abbreviation", "name"]
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
    reference = forms.ModelChoiceField(
        queryset=Reference.objects.order_by("first_author", "year", "title"),
        required=False,
        widget=ReferenceWidget(),
    )

    class Meta:
        model = Identification
        fields = [
            "identified_by",
            "taxon",
            "taxon_record",
            "reference",
            "date_identified",
            "identification_qualifier",
            "verbatim_identification",
            "identification_remarks",
        ]
        labels = {
            "identification_qualifier": "Taxon Qualifier",
            "verbatim_identification": "Taxon Verbatim",
            "identification_remarks": "Remarks",
        }
        widgets = {
            "identified_by": IdentifiedByWidget(),
            "date_identified": forms.DateInput(attrs={"type": "date"}),
            "taxon_record": TaxonWidget(model=Taxon),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["identified_by"].queryset = Person.objects.order_by(
            "last_name", "first_name"
        )
        taxon_field = self.fields["taxon_record"]
        taxon_field.queryset = Taxon.objects.filter(
            status=TaxonStatus.ACCEPTED,
            is_active=True,
        ).order_by("taxon_name")
        taxon_field.required = False
        taxon_field.widget = TaxonWidget(model=Taxon)

    def clean_identified_by(self):
        widget = self.fields["identified_by"].widget
        pending_error = getattr(widget, "_pending_validation_error", None)
        if pending_error is not None:
            widget._pending_validation_error = None
            raise pending_error

        return self.cleaned_data.get("identified_by")

    def clean(self):
        cleaned_data = super().clean()
        taxon_record = cleaned_data.get("taxon_record")
        taxon_name = cleaned_data.get("taxon")
        if taxon_record and not taxon_name:
            cleaned_data["taxon"] = taxon_record.taxon_name
        return cleaned_data


class AccessionRowSpecimenForm(BaseW3ModelForm):
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
        # Allow both legacy rank data and new accepted taxonomy schema
        qs = Taxon.objects.filter(
            Q(taxon_rank=TaxonRank.ORDER) | Q(taxon_rank__iexact="order"),
            status=TaxonStatus.ACCEPTED,
            is_active=True,
        ).distinct()
        if self.instance.pk:
            qs = qs | self.instance.taxa.all()
        self.fields["taxa"].queryset = qs.distinct()

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

    materialized_rows = list(rows)
    summary = ManualImportSummary(total_rows=len(materialized_rows))

    if not materialized_rows:
        return summary

    if queryset is None:
        queryset = Media.objects.all()

    for index, original_row in enumerate(materialized_rows, start=2):
        row = dict(original_row)
        identifier = coerce_stripped(row.get("id"))

        if default_created_by and not coerce_stripped(row.get("created_by")):
            row["created_by"] = default_created_by

        try:
            result = import_manual_row(row, queryset=queryset)
        except ManualImportError as exc:
            summary.failures.append(
                ManualImportFailure(row_number=index, identifier=identifier, message=str(exc))
            )
            continue
        except Exception as exc:  # pragma: no cover - unexpected errors bubbled to caller
            summary.failures.append(
                ManualImportFailure(row_number=index, identifier=identifier, message=str(exc))
            )
            continue

        summary.success_count += 1
        if isinstance(result, dict):
            created_records = result.get("created")
            if isinstance(created_records, list):
                summary.created_count += len(created_records)

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
