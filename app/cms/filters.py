import django_filters
from django import forms
from .models import Preparation
from django.contrib.auth import get_user_model

User = get_user_model()

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
