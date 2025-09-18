import django_filters
from django import forms
from .models import (
    Accession,
    Element,
    Locality,
    Place,
    PlaceType,
    Preparation,
    Reference,
    FieldSlip,
    DrawerRegister,
    Storage,
    Taxon,
)
from django.contrib.auth import get_user_model

User = get_user_model()

class AccessionFilter(django_filters.FilterSet):
    specimen_no = django_filters.CharFilter(
        lookup_expr='exact',
        label="Specimen No.",
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    specimen_prefix = django_filters.ModelChoiceFilter(
        queryset=Locality.objects.all(),
        label="Prefix",
        widget=forms.Select(attrs={'class': 'w3-select'})
    )
    specimen_suffix = django_filters.CharFilter(
        lookup_expr='icontains',
        label="Suffix",
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    comment = django_filters.CharFilter(
        lookup_expr='icontains',
        label="Comment",
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    taxon = django_filters.ModelChoiceFilter(
        queryset=Taxon.objects.order_by('taxon_name'),
        label="Taxon",
        method='filter_by_taxon',
        widget=forms.Select(attrs={'class': 'w3-select'})
    )
    element = django_filters.ModelChoiceFilter(
        queryset=Element.objects.order_by('name'),
        label="Element",
        method='filter_by_element',
        widget=forms.Select(attrs={'class': 'w3-select'})
    )
    family = django_filters.CharFilter(
        label="Family",
        method='filter_by_family',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    subfamily = django_filters.CharFilter(
        label="Subfamily",
        method='filter_by_subfamily',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    tribe = django_filters.CharFilter(
        label="Tribe",
        method='filter_by_tribe',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    genus = django_filters.CharFilter(
        label="Genus",
        method='filter_by_genus',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    species = django_filters.CharFilter(
        label="Species",
        method='filter_by_species',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )

    class Meta:
        model = Accession
        fields = [
            'specimen_no',
            'specimen_prefix',
            'specimen_suffix',
            'comment',
            'taxon',
            'element',
            'family',
            'subfamily',
            'tribe',
            'genus',
            'species',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['taxon'].field.empty_label = 'Any Taxon'
        self.filters['element'].field.empty_label = 'Any Element'

    def filter_by_taxon(self, queryset, name, value):
        if value:
            return queryset.filter(
                accessionrow__identification__taxon__iexact=value.taxon_name
            ).distinct()
        return queryset

    def filter_by_element(self, queryset, name, value):
        if value:
            return queryset.filter(
                accessionrow__natureofspecimen__element=value
            ).distinct()
        return queryset

    def _filter_by_taxon_attribute(self, queryset, attribute, value):
        if not value:
            return queryset
        matching_taxa = Taxon.objects.filter(
            **{f"{attribute}__icontains": value}
        ).values_list('taxon_name', flat=True)
        if not matching_taxa:
            return queryset.none()
        return queryset.filter(
            accessionrow__identification__taxon__in=matching_taxa
        ).distinct()

    def filter_by_family(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, 'family', value)

    def filter_by_subfamily(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, 'subfamily', value)

    def filter_by_tribe(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, 'tribe', value)

    def filter_by_genus(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, 'genus', value)

    def filter_by_species(self, queryset, name, value):
        return self._filter_by_taxon_attribute(queryset, 'species', value)


class PreparationFilter(django_filters.FilterSet):
    ...
    status = django_filters.ChoiceFilter(
        choices=Preparation._meta.get_field('status').choices,
        widget=forms.Select(attrs={'class': 'w3-select'})
    )

    approval_status = django_filters.ChoiceFilter(
        choices=Preparation._meta.get_field('approval_status').choices,
        widget=forms.Select(attrs={'class': 'w3-select'})
    )

    preparator = django_filters.ModelChoiceFilter(
        queryset=User.objects.none(),
        widget=forms.Select(attrs={'class': 'w3-select'})
    )

    started_on = django_filters.DateFromToRangeFilter(
        label="Started Between",
        widget=django_filters.widgets.RangeWidget(
            attrs={'type': 'date', 'class': 'w3-input'}
        )
    )
    completed_on = django_filters.DateFromToRangeFilter(
        label="Completed Between",
        widget=django_filters.widgets.RangeWidget(
            attrs={'type': 'date', 'class': 'w3-input'}
        )
    )
    
    accession_label = django_filters.CharFilter(
        field_name='accession_label',
        lookup_expr='icontains',
        label='Accession Label',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['preparator'].queryset = User.objects.all()

    class Meta:
        model = Preparation
        fields = ['accession_label', 'status', 'approval_status', 'preparator', 'started_on', 'completed_on']



class LocalityFilter(django_filters.FilterSet):

    abbreviation = django_filters.CharFilter(
        lookup_expr='exact',
        label="Abbreviation",
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    name = django_filters.ModelChoiceFilter(
        queryset=Locality.objects.all(),
        label="Name",
        widget=forms.Select(attrs={'class': 'w3-select'})
    )
 
 

    class Meta:
        model = Locality
        fields = ['abbreviation', 'name']


class PlaceFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Name',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    place_type = django_filters.ChoiceFilter(
        choices=PlaceType.choices,
        label='Type',
        widget=forms.Select(attrs={'class': 'w3-select'})
    )
    locality = django_filters.ModelChoiceFilter(
        queryset=Locality.objects.all(),
        label='Locality',
        widget=forms.Select(attrs={'class': 'w3-select'})
    )

    class Meta:
        model = Place
        fields = ['name', 'place_type', 'locality']


class ReferenceFilter(django_filters.FilterSet):
    first_author = django_filters.CharFilter(
        lookup_expr='icontains',
        label='First Author',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    year = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Year',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )
    title = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Title',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )

    class Meta:
        model = Reference
        fields = ['first_author', 'year', 'title']


class FieldSlipFilter(django_filters.FilterSet):
    collector = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Collector',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )

    collection_date = django_filters.DateFromToRangeFilter(
        label='Collection Date',
        widget=django_filters.widgets.RangeWidget(
            attrs={'type': 'date', 'class': 'w3-input'}
        )
    )

    verbatim_locality = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Verbatim Locality',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )

    verbatim_taxon = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Verbatim Taxon',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )

    verbatim_element = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Verbatim Element',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )

    verbatim_horizon = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Verbatim Horizon',
        widget=forms.TextInput(attrs={'class': 'w3-input'})
    )

    class Meta:
        model = FieldSlip
        fields = [
            'collector',
            'collection_date',
            'verbatim_locality',
            'verbatim_taxon',
            'verbatim_element',
            'verbatim_horizon',
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
        queryset=Taxon.objects.filter(taxon_rank__iexact="order"),
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

