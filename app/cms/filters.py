import django_filters
from django import forms
from .models import (
    Accession,
    Locality,
    Place,
    PlaceType,
    Preparation,
    Reference,
    FieldSlip,
    DrawerRegister,
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

    class Meta:
        model = Accession
        fields = ['specimen_no', 'specimen_prefix', 'specimen_suffix', 'comment']


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

