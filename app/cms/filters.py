import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from .models import (
    Accession,
    DrawerRegister,
    FieldSlip,
    Locality,
    Organisation,
    Place,
    PlaceType,
    Preparation,
    Reference,
    Storage,
    Taxon,
    TaxonRank,
    TaxonStatus,
    SpecimenListPage,
    SpecimenListRowCandidate,
)
from django.contrib.auth import get_user_model

User = get_user_model()


def _matching_taxon_names(attribute: str, value: str) -> set[str]:
    taxa = Taxon.objects.filter(
        status=TaxonStatus.ACCEPTED,
        is_active=True,
        **{f"{attribute}__icontains": value},
    )
    return set(taxa.values_list("taxon_name", flat=True))


def _ensure_widget_has_w3_class(widget, fallback_class: str = "w3-input") -> None:
    classes = widget.attrs.get("class", "")
    tokens = [token for token in classes.split() if token]
    if any(token.startswith("w3-") for token in tokens):
        return
    widget.attrs["class"] = " ".join(tokens + [fallback_class]).strip()


def _ensure_filters_use_w3_styles(filters: dict[str, django_filters.Filter]) -> None:
    for filter_field in filters.values():
        widget = filter_field.field.widget
        if hasattr(widget, "widgets"):
            for subwidget in widget.widgets:
                _ensure_widget_has_w3_class(subwidget)
        else:
            _ensure_widget_has_w3_class(widget)


class AccessionFilter(django_filters.FilterSet):
    specimen_no = django_filters.CharFilter(
        lookup_expr="exact",
        label="Specimen No.",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    specimen_prefix = django_filters.ModelChoiceFilter(
        queryset=Locality.objects.all(),
        label="Prefix",
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    specimen_suffix = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Suffix",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    comment = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Comment",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    taxon = django_filters.CharFilter(
        label="Taxon",
        method="filter_by_taxon",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    element = django_filters.CharFilter(
        label="Element",
        method="filter_by_element",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    family = django_filters.CharFilter(
        label="Family",
        method="filter_by_family",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    subfamily = django_filters.CharFilter(
        label="Subfamily",
        method="filter_by_subfamily",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    tribe = django_filters.CharFilter(
        label="Tribe",
        method="filter_by_tribe",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    genus = django_filters.CharFilter(
        label="Genus",
        method="filter_by_genus",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    species = django_filters.CharFilter(
        label="Species",
        method="filter_by_species",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )

    organisation = django_filters.ModelChoiceFilter(
        queryset=Organisation.objects.none(),
        label=_("Organisation"),
        method="filter_by_organisation",
        widget=forms.Select(attrs={"class": "w3-select"}),
    )

    class Meta:
        model = Accession
        fields = [
            "specimen_no",
            "specimen_prefix",
            "specimen_suffix",
            "comment",
            "taxon",
            "element",
            "family",
            "subfamily",
            "tribe",
            "genus",
            "species",
            "organisation",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organisation_filter = self.filters["organisation"]
        organisation_filter.queryset = Organisation.objects.filter(is_active=True).order_by(
            "name"
        )

        request = getattr(self, "request", None)
        if not request or not getattr(request, "user", None):
            return

        user = request.user
        if user.is_superuser:
            return

        membership = getattr(user, "organisation_membership", None)
        organisation = getattr(membership, "organisation", None)
        if organisation is None:
            return

        organisation_filter.queryset = organisation_filter.queryset.filter(pk=organisation.pk)

    def filter_by_organisation(self, queryset, name, value):
        if not value:
            return queryset

        return queryset.filter(
            accessioned_by__organisation_membership__organisation=value
        ).distinct()

    def filter_by_taxon(self, queryset, name, value):
        if not value:
            return queryset
        taxon_q = Q(accessionrow__identification__taxon_verbatim__icontains=value)
        taxon_q |= Q(accessionrow__identification__taxon__icontains=value)
        taxon_q |= Q(
            accessionrow__identification__taxon_record__taxon_name__icontains=value
        )
        taxon_q |= Q(
            accessionrow__identification__taxon_record__synonyms__taxon_name__icontains=value
        )
        return queryset.filter(taxon_q).distinct()

    def filter_by_element(self, queryset, name, value):
        if value:
            return queryset.filter(
                accessionrow__natureofspecimen__element__name__icontains=value
            ).distinct()
        return queryset

    def _filter_by_taxon_attribute(self, queryset, attribute, value):
        if not value:
            return queryset
        lookup = {
            f"accessionrow__identification__taxon_record__{attribute}__icontains": value
        }
        matching_names = _matching_taxon_names(attribute, value)
        name_filter = Q(**lookup)
        if matching_names:
            name_filter |= Q(
                accessionrow__identification__taxon_verbatim__in=matching_names
            )
            name_filter |= Q(accessionrow__identification__taxon__in=matching_names)
        return queryset.filter(name_filter).distinct()

    def filter_by_family(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, "family", value)


    def filter_by_subfamily(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, "subfamily", value)

    def filter_by_tribe(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, "tribe", value)

    def filter_by_genus(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, "genus", value)

    def filter_by_species(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, "species", value)


class SpecimenListPageFilter(django_filters.FilterSet):
    source_label = django_filters.CharFilter(
        field_name="pdf__source_label",
        lookup_expr="icontains",
        label=_("Source label"),
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    pipeline_status = django_filters.ChoiceFilter(
        choices=SpecimenListPage.PipelineStatus.choices,
        label=_("Pipeline status"),
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    classification_status = django_filters.ChoiceFilter(
        choices=SpecimenListPage.ClassificationStatus.choices,
        label=_("Classification status"),
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    min_confidence = django_filters.NumberFilter(
        field_name="classification_confidence",
        lookup_expr="gte",
        label=_("Minimum confidence"),
        widget=forms.NumberInput(attrs={"class": "w3-input", "step": "0.01", "min": "0", "max": "1"}),
    )
    page_type = django_filters.ChoiceFilter(
        choices=SpecimenListPage.PageType.choices,
        label=_("Page type"),
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    assigned_reviewer = django_filters.ModelChoiceFilter(
        queryset=User.objects.none(),
        label=_("Assigned reviewer"),
        widget=forms.Select(attrs={"class": "w3-select"}),
    )

    class Meta:
        model = SpecimenListPage
        fields = [
            "source_label",
            "pipeline_status",
            "classification_status",
            "min_confidence",
            "page_type",
            "assigned_reviewer",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["assigned_reviewer"].queryset = User.objects.order_by("username")
        _ensure_filters_use_w3_styles(self.filters)


class SpecimenListRowCandidateFilter(django_filters.FilterSet):
    source_label = django_filters.CharFilter(
        field_name="page__pdf__source_label",
        lookup_expr="icontains",
        label=_("Source label"),
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    page_number = django_filters.NumberFilter(
        field_name="page__page_number",
        label=_("Page number"),
        widget=forms.NumberInput(attrs={"class": "w3-input", "min": "1"}),
    )
    page_type = django_filters.ChoiceFilter(
        field_name="page__page_type",
        choices=SpecimenListPage.PageType.choices,
        label=_("Page type"),
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    status = django_filters.ChoiceFilter(
        choices=SpecimenListRowCandidate.ReviewStatus.choices,
        label=_("Row status"),
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    min_confidence = django_filters.NumberFilter(
        field_name="confidence",
        lookup_expr="gte",
        label=_("Minimum confidence"),
        widget=forms.NumberInput(attrs={"class": "w3-input", "step": "0.01", "min": "0", "max": "1"}),
    )
    max_confidence = django_filters.NumberFilter(
        field_name="confidence",
        lookup_expr="lte",
        label=_("Maximum confidence"),
        widget=forms.NumberInput(attrs={"class": "w3-input", "step": "0.01", "min": "0", "max": "1"}),
    )
    assigned_reviewer = django_filters.ModelChoiceFilter(
        queryset=User.objects.none(),
        label=_("Assigned reviewer"),
        widget=forms.Select(attrs={"class": "w3-select"}),
    )

    class Meta:
        model = SpecimenListRowCandidate
        fields = [
            "source_label",
            "page_number",
            "page_type",
            "status",
            "min_confidence",
            "max_confidence",
            "assigned_reviewer",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["assigned_reviewer"].queryset = User.objects.order_by("username")
        _ensure_filters_use_w3_styles(self.filters)


class PreparationFilter(django_filters.FilterSet):
    ...
    status = django_filters.ChoiceFilter(
        choices=Preparation._meta.get_field("status").choices,
        widget=forms.Select(attrs={"class": "w3-select"}),
    )

    approval_status = django_filters.ChoiceFilter(
        choices=Preparation._meta.get_field("approval_status").choices,
        widget=forms.Select(attrs={"class": "w3-select"}),
    )

    preparator = django_filters.ModelChoiceFilter(
        queryset=User.objects.none(), widget=forms.Select(attrs={"class": "w3-select"})
    )

    started_on = django_filters.DateFromToRangeFilter(
        label="Started Between",
        widget=django_filters.widgets.RangeWidget(
            attrs={"type": "date", "class": "w3-input"}
        ),
    )
    completed_on = django_filters.DateFromToRangeFilter(
        label="Completed Between",
        widget=django_filters.widgets.RangeWidget(
            attrs={"type": "date", "class": "w3-input"}
        ),
    )

    accession_label = django_filters.CharFilter(
        field_name="accession_label",
        lookup_expr="icontains",
        label="Accession Label",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["preparator"].queryset = User.objects.all()
        _ensure_filters_use_w3_styles(self.filters)

    class Meta:
        model = Preparation
        fields = [
            "accession_label",
            "status",
            "approval_status",
            "preparator",
            "started_on",
            "completed_on",
        ]


class LocalityFilter(django_filters.FilterSet):

    abbreviation = django_filters.CharFilter(
        lookup_expr="exact",
        label="Abbreviation",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    name = django_filters.ModelChoiceFilter(
        queryset=Locality.objects.all(),
        label="Name",
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    geological_times = django_filters.MultipleChoiceFilter(
        choices=Locality.GeologicalTime.choices,
        label=_("Geological time"),
        widget=forms.SelectMultiple(attrs={"class": "w3-select"}),
        method="filter_geological_times",
    )

    class Meta:
        model = Locality
        fields = ["abbreviation", "name", "geological_times"]

    def filter_geological_times(self, queryset, name, value):
        if not value:
            return queryset

        conditions = Q()
        for choice in value:
            conditions |= Q(geological_times__contains=[choice])

        if not conditions:
            return queryset

        return queryset.filter(conditions)


class PlaceFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Name",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    place_type = django_filters.ChoiceFilter(
        choices=PlaceType.choices,
        label="Type",
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    locality = django_filters.ModelChoiceFilter(
        queryset=Locality.objects.all(),
        label="Locality",
        widget=forms.Select(attrs={"class": "w3-select"}),
    )

    class Meta:
        model = Place
        fields = ["name", "place_type", "locality"]


class ReferenceFilter(django_filters.FilterSet):
    first_author = django_filters.CharFilter(
        lookup_expr="icontains",
        label="First Author",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    year = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Year",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    title = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Title",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )

    class Meta:
        model = Reference
        fields = ["first_author", "year", "title"]


class FieldSlipFilter(django_filters.FilterSet):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _ensure_filters_use_w3_styles(self.filters)
    field_number = django_filters.CharFilter(
        lookup_expr="icontains",
        label=_("Field Number"),
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    collector = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Collector",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )

    collection_date = django_filters.DateFromToRangeFilter(
        label="Collection Date",
        widget=django_filters.widgets.RangeWidget(
            attrs={"type": "date", "class": "w3-input"}
        ),
    )

    verbatim_locality = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Verbatim Locality",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )

    verbatim_taxon = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Verbatim Taxon",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )

    verbatim_element = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Verbatim Element",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )

    verbatim_horizon = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Verbatim Horizon",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )

    class Meta:
        model = FieldSlip
        fields = [
            "field_number",
            "collector",
            "collection_date",
            "verbatim_locality",
            "verbatim_taxon",
            "verbatim_element",
            "verbatim_horizon",
        ]


class DrawerRegisterFilter(django_filters.FilterSet):
    code = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Code",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    scanning_status = django_filters.ChoiceFilter(
        choices=DrawerRegister.ScanningStatus.choices,
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    localities = django_filters.ModelChoiceFilter(
        queryset=Locality.objects.all(),
        label="Locality",
        widget=forms.Select(attrs={"class": "w3-select"}),
    )
    taxa = django_filters.ModelChoiceFilter(
        queryset=Taxon.objects.filter(
            Q(taxon_rank=TaxonRank.ORDER) | Q(taxon_rank__iexact="order"),
            status=TaxonStatus.ACCEPTED,
            is_active=True,
        )
        .distinct()
        .order_by("taxon_name"),
        label="Taxon",
        widget=forms.Select(attrs={"class": "w3-select"}),
    )

    class Meta:
        model = DrawerRegister
        fields = ["code", "scanning_status", "localities", "taxa"]


class StorageFilter(django_filters.FilterSet):
    area = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Area",
        widget=forms.TextInput(attrs={"class": "w3-input"}),
    )
    parent_area = django_filters.ModelChoiceFilter(
        queryset=Storage.objects.all(),
        label="Parent Area",
        widget=forms.Select(attrs={"class": "w3-select"}),
    )

    class Meta:
        model = Storage
        fields = ["area", "parent_area"]
