from django import forms
from .models import FieldSlip, Media

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

            'field_number': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'discoverer': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'collector': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'collection_date': forms.DateInput(attrs={'class': 'fieldslip_form_input', 'type': 'date'}),

            'verbatim_locality': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'verbatim_taxon': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),
            'verbatim_element': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'verbatim_horizon': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'verbatim_latitude': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'verbatim_longitude': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'verbatim_SRS': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'verbatim_coordinate_system': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'verbatim_elevation': forms.TextInput(attrs={'class': 'fieldslip_form_input'}),

            'aerial_photo': forms.FileInput(attrs={'class': 'fieldslip_form_input'}),

        }

class MediaUploadForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = ['media_location', 'type', 'format', 'license', 'rights_holder']
