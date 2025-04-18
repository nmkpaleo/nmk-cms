from django import forms
from django_select2 import forms as s2forms
from django_select2.forms import ModelSelect2Widget, Select2Widget

from .models import (Accession, AccessionFieldSlip, AccessionReference,
                     AccessionRow, Comment, FieldSlip, Identification, Media,
                     NatureOfSpecimen, Preparation, Reference, SpecimenGeology)

class AccessionRowWidget(s2forms.ModelSelect2Widget):
    search_fields = [
        "accession__collection__description__icontains",
        "accession__specimen_prefix__abbreviation__icontains",
        "accession__specimen_no__icontains",
        "specimen_suffix__icontains"
    ]

    def label_from_instance(self, obj):
        """
        Custom label for dropdown: Show full accession with suffix and collection name
        """
        collection = obj.accession.collection.description if obj.accession.collection else "Unknown Collection"
        prefix = obj.accession.specimen_prefix.abbreviation
        number = obj.accession.specimen_no
        suffix = obj.specimen_suffix or "-"
        return f"{prefix} {number}{suffix} ({collection})"

class FieldSlipWidget(s2forms.ModelSelect2Widget):
    search_fields = ["field_number__icontains", "verbatim_locality__icontains"]

    def label_from_instance(self, obj):
        """
        Custom label for dropdown: Show field_number + verbatim_locality
        """
        return f"{obj.field_number} - {obj.verbatim_locality if obj.verbatim_locality else 'No locality'}"

class ElementWidget(s2forms.ModelSelect2Widget):
    search_fields = [
        "name__icontains",
        ]

class ReferenceWidget(s2forms.ModelSelect2Widget):
    search_fields = [
        "title__icontains",
        "first_author__icontains",
        ]
    
class TaxonWidget(s2forms.ModelSelect2Widget):
    search_fields = [
        "taxon_name__icontains",
        ]

class AccessionForm(forms.ModelForm):
    class Meta:
        model = Accession
        fields = [
            'collection', 'specimen_prefix', 'specimen_no', 'accessioned_by',
            'type_status', 'comment', 'is_published'
        ]

class AccessionCommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['subject', 'comment', 'comment_by']

class AccessionFieldSlipForm(forms.ModelForm):
    class Meta:
        model = AccessionFieldSlip
        fields = ["fieldslip", "notes"]
        widgets = {
            "fieldslip": FieldSlipWidget,}

class AccessionGeologyForm(forms.ModelForm):
    class Meta:
        model = SpecimenGeology
        fields = ['earliest_geological_context', 'latest_geological_context']

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
    collection_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )

    class Meta:
        model = FieldSlip
        fields = [
            'field_number', 'discoverer', 'collector', 'collection_date',
            'verbatim_locality', 'verbatim_taxon', 'verbatim_element',
            'verbatim_horizon', 'aerial_photo', 'verbatim_latitude',
            'verbatim_longitude', 'verbatim_SRS', 'verbatim_coordinate_system',
            'verbatim_elevation'
        ]

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
        fields = ['media_location', 'type', 'license', 'rights_holder']

class AddAccessionRowForm(forms.ModelForm):
    specimen_suffix = forms.ChoiceField(choices=[], required=True)  # Empty choices initially
    accession = forms.ModelChoiceField(
        queryset=Accession.objects.all(),
        widget=forms.HiddenInput()  # Ensure it's hidden in the form
    )
    class Meta:
        model = AccessionRow
        fields = ['accession', 'storage', 'specimen_suffix']

    def __init__(self, *args, **kwargs):
        """ Dynamically populate specimen_suffix choices based on the accession """
        accession = kwargs.pop('accession', None)  # Get accession from kwargs

        super().__init__(*args, **kwargs)

        if accession:
            self.fields['accession'].initial = accession  # Set initial accession value
            self.fields['specimen_suffix'].choices = self.get_available_specimen_suffixes(accession)

    def get_available_specimen_suffixes(self, accession):
        """ Returns a list of available specimen_suffix options """
        taken_suffixes = set(
            AccessionRow.objects.filter(accession=accession)
            .values_list('specimen_suffix', flat=True)
        )
        all_valid_suffixes = AccessionRow().generate_valid_suffixes()  # Get valid suffixes
        available_suffixes = [("-", "-")]  # Default choice
        
        for suffix in all_valid_suffixes:
            if suffix not in taken_suffixes:
                available_suffixes.append((suffix, suffix))

        return available_suffixes

class NatureOfSpecimenForm(forms.ModelForm):
    class Meta:
        model = NatureOfSpecimen
        fields = ['element', 'side', 'condition', 'verbatim_element', 'portion', 'fragments']

class AddSpecimenForm(forms.ModelForm):
    accession_row = forms.ModelChoiceField(
        queryset=AccessionRow.objects.all(),
        widget=forms.HiddenInput()  # Ensure it's hidden in the form
    )
    class Meta:
        model = NatureOfSpecimen
        fields = ['element', 'side', 'condition', 'verbatim_element', 'portion', 'fragments']

    def __init__(self, *args, **kwargs):
        accession_row = kwargs.pop('accession_row', None)  # Get accession from kwargs

        super().__init__(*args, **kwargs)

        if accession_row:
            self.fields['accession_row'].initial = accession_row  # Set initial accession_row value

class AccessionRowIdentificationForm(forms.ModelForm):
    class Meta:
        model = Identification
        fields = ['identified_by', 'taxon', 'reference', 'date_identified', 'identification_qualifier', 'verbatim_identification', 'identification_remarks']
        widgets = {"reference": ReferenceWidget}
        labels = {
            'identification_qualifier': 'Taxon Qualifier',
            'verbatim_identification': 'Taxon Verbatim',
            'identification_remarks': 'Remarks',
        }

class AccessionRowSpecimenForm(forms.ModelForm):
    class Meta:
        model = NatureOfSpecimen
        fields = ['element', 'side', 'condition', 'verbatim_element', 'portion', 'fragments']
        widgets = {
            "element": ElementWidget,}

class PreparationForm(forms.ModelForm):
    """ Form for creating/updating preparation records. """
    
    class Meta:
        model = Preparation
        fields = [
            "accession_row", "preparation_type", "reason", "preparator", "curator", "status", "started_on", "completed_on",
            "original_storage", "temporary_storage", "condition_before", "condition_after",
            "preparation_method", "chemicals_used", "materials_used", "notes"
        ]
        widgets = {
            "started_on": forms.DateInput(attrs={"type": "date"}),
            "completed_on": forms.DateInput(attrs={"type": "date"}),
            "accession_row": AccessionRowWidget
        }

class PreparationApprovalForm(forms.ModelForm):
    """ Form for curators to approve or decline a preparation. """
    
    class Meta:
        model = Preparation
        fields = ["approval_status", "curator_comments"]

class PreparationMediaUploadForm(forms.Form):
    media_files = forms.FileField(
        widget=forms.FileInput(attrs={'multiple': False}),
        label="Upload media files"
    )
    context = forms.ChoiceField(
        choices=[
            ("before", "Before Preparation"),
            ("after", "After Preparation"),
            ("in_progress", "In Progress"),
            ("other", "Other")
        ],
        initial="before"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2})
    )