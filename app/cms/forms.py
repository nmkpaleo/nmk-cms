from django import forms
from django_select2 import forms as s2forms
from django_select2.forms import ModelSelect2Widget
from .models import Accession, AccessionReference, AccessionRow, FieldSlip, Media, Reference

class ReferenceWidget(s2forms.ModelSelect2Widget):
    search_fields = [
        "title__icontains",
        "first_author__icontains",
        ]
    
class AccessionReferenceForm(forms.ModelForm):
    class Meta:
        model = AccessionReference
        fields = ['reference', 'page']
        widgets = {
            "reference": ReferenceWidget,}

class AccessionReferenceForm2(forms.ModelForm):
    reference = forms.ModelChoiceField(
        queryset=Reference.objects.all(),
        widget=ModelSelect2Widget(
            model=Reference,
            search_fields=['title__icontains'],  # Allows searching by title
            attrs={'data-placeholder': 'Select References...'}
        )
    )

    class Meta:
        model = AccessionReference
        fields = ['reference', 'page']

class FieldSlipForm(forms.ModelForm):
    class Meta:
        model = FieldSlip
        fields = [
            'field_number', 'discoverer', 'collector', 'collection_date',
            'verbatim_locality', 'verbatim_taxon', 'verbatim_element',
            'verbatim_horizon', 'aerial_photo', 'verbatim_latitude',
            'verbatim_longitude', 'verbatim_SRS', 'verbatim_coordinate_system',
            'verbatim_elevation'
        ]
        widgets = {

            'field_number': forms.TextInput(attrs={'class': 'template_form_input'}),

            'discoverer': forms.TextInput(attrs={'class': 'template_form_input'}),

            'collector': forms.TextInput(attrs={'class': 'template_form_input'}),

            'collection_date': forms.DateInput(attrs={'class': 'template_form_input', 'type': 'date'}),

            'verbatim_locality': forms.TextInput(attrs={'class': 'template_form_input'}),

            'verbatim_taxon': forms.TextInput(attrs={'class': 'template_form_input'}),
            'verbatim_element': forms.TextInput(attrs={'class': 'template_form_input'}),

            'verbatim_horizon': forms.TextInput(attrs={'class': 'template_form_input'}),

            'verbatim_latitude': forms.TextInput(attrs={'class': 'template_form_input'}),

            'verbatim_longitude': forms.TextInput(attrs={'class': 'template_form_input'}),

            'verbatim_SRS': forms.TextInput(attrs={'class': 'template_form_input'}),

            'verbatim_coordinate_system': forms.TextInput(attrs={'class': 'template_form_input'}),

            'verbatim_elevation': forms.TextInput(attrs={'class': 'template_form_input'}),

            'aerial_photo': forms.FileInput(attrs={'class': 'template_form_input'}),

        }


class ReferenceForm(forms.ModelForm):
    class Meta:
        model = Reference
        fields = [

            'title', 'first_author', 'year', 'journal', 'volume', 'issue', 'pages', 'doi', 'citation'
        ]
        widgets = {

            'title': forms.TextInput(attrs={'class': 'template_form_input'}),

            'first_author': forms.TextInput(attrs={'class': 'template_form_input'}),

            'year': forms.TextInput(attrs={'class': 'template_form_input', 'type': 'year'}),

            'journal': forms.DateInput(attrs={'class': 'template_form_input'}),

            'volume': forms.TextInput(attrs={'class': 'template_form_input'}),

            'issue': forms.TextInput(attrs={'class': 'template_form_input'}),

            'pages': forms.TextInput(attrs={'class': 'template_form_input'}),

            'doi': forms.TextInput(attrs={'class': 'template_form_input'}),

            'citation': forms.TextInput(attrs={'class': 'template_form_input'})

        }


class MediaUploadForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = ['media_location', 'type', 'format', 'license', 'rights_holder']

class AddAccessionRowForm(forms.ModelForm):
    class Meta:
        model = AccessionRow
        fields = ['storage', 'specimen_suffix']

