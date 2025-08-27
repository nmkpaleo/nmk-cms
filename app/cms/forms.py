from dal import autocomplete
from django import forms
from django.contrib.auth import get_user_model
from django_select2 import forms as s2forms
from django_select2.forms import ModelSelect2Widget, Select2Widget
from django.contrib.auth.models import User
from django.urls import reverse_lazy

from .models import (Accession, AccessionFieldSlip, AccessionNumberSeries, AccessionReference,
                     AccessionRow, Collection, Comment, Element, FieldSlip, Identification,
                     Locality, Media,
                     NatureOfSpecimen, Person, Preparation, Reference, SpecimenGeology,
                     DrawerRegister, Taxon)

import json

User = get_user_model()

class AccessionBatchForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all())
    count = forms.IntegerField(min_value=1, max_value=500)
    collection = forms.ModelChoiceField(queryset=Collection.objects.all())
    specimen_prefix = forms.ModelChoiceField(queryset=Locality.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_users = User.objects.filter(accession_series__is_active=True).distinct()
        self.fields['user'].queryset = active_users.order_by('username')
        self.fields['user'].help_text = "Only users with active accession number series are shown."
        self.fields['user'].label_from_instance = self.user_label_with_remaining

    def user_label_with_remaining(self, user):
        series = user.accession_series.filter(is_active=True).first()
        if series:
            remaining = series.end_at - series.current_number + 1
            return f"{user.get_full_name() or user.username} ({remaining} accessions available)"
        return user.get_full_name() or user.username

class AccessionNumberSelectForm(forms.Form):
    accession_number = forms.ChoiceField(label="Select Accession Number", choices=[])
    
    def __init__(self, *args, **kwargs):
        available_numbers = kwargs.pop("available_numbers", [])
        super().__init__(*args, **kwargs)
        self.fields["accession_number"].choices = [(n, n) for n in available_numbers]

class AccessionNumberSeriesAdminForm(forms.ModelForm):
    count = forms.IntegerField(
        label="Count",
        min_value=1,
        required=True,
        help_text="Number of accession numbers to generate.",
    )

    class Meta:
        model = AccessionNumberSeries
        fields = ['user', 'start_from', 'current_number', 'is_active']  # exclude 'count'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from django.contrib.auth import get_user_model
        import json
        from .models import AccessionNumberSeries
        User = get_user_model()

        # Always add count to the form manually
        self.fields['count'] = forms.IntegerField(
            label="Count",
            min_value=1,
            required=True,
            help_text="Number of accession numbers to generate or total range size."
        )

        if self.instance.pk:
            # Change view: show disabled count value
            total = (
                self.instance.end_at - self.instance.start_from + 1
                if self.instance.end_at and self.instance.start_from
                else 0
            )
            self.fields['count'].initial = total
            self.fields['count'].disabled = True
        else:
            # Add view: make start_from and current_number readonly
            for field_name in ['start_from', 'current_number']:
                if field_name in self.fields:
                    self.fields[field_name].widget.attrs['readonly'] = True
            self.fields['is_active'].initial = True
            self.fields['is_active'].widget = forms.HiddenInput()
            
        # Inject JS data for user field
        if 'user' in self.fields:
            mary_series = AccessionNumberSeries.objects.filter(user__username__iexact='mary').order_by('-end_at').first()
            shared_series = AccessionNumberSeries.objects.exclude(user__username__iexact='mary').order_by('-end_at').first()

            series_map = {
                "mary": mary_series.end_at + 1 if mary_series and mary_series.end_at else 1_000_000,
                "shared": shared_series.end_at + 1 if shared_series and shared_series.end_at else 1
            }

            self.fields['user'].widget.attrs['data-series-starts'] = json.dumps(series_map)
            self.fields['user'].label_from_instance = lambda obj: obj.username  # ensure username shown

    def _build_series_map(self):
        series_map = {}
        for user in User.objects.all():
            qs = AccessionNumberSeries.objects.filter(user=user).order_by('-end_at')
            base = 1_000_000 if user.username.lower() == 'mary' else 1

            if qs.exists() and qs.first().end_at is not None:
                next_start = qs.first().end_at + 1
            else:
                next_start = base

            series_map[user.username.lower()] = next_start
            self.fields['user'].widget.attrs['data-series-starts'] = json.dumps({
                "mary": 1_000_000,
                "default": 1
            })
            self.fields['user'].label_from_instance = lambda obj: obj.username

        return json.dumps(series_map)

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get("user")

        if not self.instance.pk and user:
            from .models import AccessionNumberSeries
            if AccessionNumberSeries.objects.filter(user=user, is_active=True).exists():
                self.add_error("user", "This user already has an active accession number series.")
        return cleaned_data

    def save(self, commit=True):
        if not self.instance.pk:
            count = self.cleaned_data.get("count")
            if count:
                self.instance.end_at = self.instance.start_from + count - 1
        return super().save(commit=commit)
        
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

class AccessionMediaUploadForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = ['media_location', 'type', 'license', 'rights_holder']
        widgets = {
            'media_location': forms.ClearableFileInput(attrs={'multiple': False}),
        }

class FieldSlipWidget(autocomplete.ModelSelect2):
    search_fields = ["field_number__icontains", "verbatim_locality__icontains"]

    def __init__(self, *args, **kwargs):
        kwargs["url"] = reverse_lazy("fieldslip-autocomplete")
        kwargs["attrs"] = {
            "data-placeholder": "Search Field Slips...",
            "data-minimum-input-length": 1,
        }
        super().__init__(*args, **kwargs)

    class Media:
        # ONLY load DAL’s compatible JS and CSS
        js = (
            "autocomplete_light/jquery.init.js",
            "autocomplete_light/autocomplete_light.js",
            "autocomplete_light/autocomplete.init.js",
        )
        css = {
            'screen': [
                'autocomplete_light/select2.css',
                'autocomplete_light/autocomplete.css',
            ]
        }

    def label_from_instance(self, obj):
        return f"{obj.field_number} - {obj.verbatim_locality or 'No locality'}"

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
            'type_status', 'comment',
        ]
        widgets = {
            'accessioned_by': forms.HiddenInput(),
#            'specimen_no': forms.TextInput(attrs={'readonly': True, 'disabled': True}),  # still display, not editable
            'specimen_no': forms.TextInput(attrs={'readonly': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make 'specimen_no' disabled (visible but not editable)
#        self.fields['specimen_no'].disabled = True
        # Custom label for Locality field in dropdown
        self.fields['specimen_prefix'].label_from_instance = lambda obj: f"{obj.abbreviation} - {obj.name}"
        
class AccessionCommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['subject', 'comment', 'comment_by']

class AccessionFieldSlipForm(forms.ModelForm):
    class Meta:
        model = AccessionFieldSlip
        fields = ["fieldslip", "notes"]
        widgets = {
            "fieldslip": FieldSlipWidget(url=reverse_lazy("fieldslip-autocomplete")),
        }

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

class LocalityForm(forms.ModelForm):
    class Meta:
        model = Locality
        fields = [

            'abbreviation', 'name'
        ]
        widgets = {

            'abbreviation': forms.TextInput(attrs={'class': 'template_form_input'}),

            'name': forms.TextInput(attrs={'class': 'template_form_input'})

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
    
class SpecimenCompositeForm(forms.Form):
    storage = forms.ModelChoiceField(
        queryset=AccessionRow._meta.get_field('storage').related_model.objects.all(),
        required=True,
        empty_label="Select a storage location",
    )

    element = forms.ModelChoiceField(queryset=Element.objects.all(), required=True)
    side = forms.CharField(max_length=50, required=False)
    condition = forms.CharField(max_length=255, required=False)
    fragments = forms.IntegerField(min_value=0, required=False)
    taxon = forms.CharField(max_length=255, required=False)
    identified_by = forms.ModelChoiceField(queryset=Person.objects.all(), required=False)


class DrawerRegisterForm(forms.ModelForm):
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
        self.fields["taxa"].queryset = Taxon.objects.filter(taxon_rank="order")

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("scanning_status")
        users = cleaned_data.get("scanning_users")
        if status == DrawerRegister.ScanningStatus.IN_PROGRESS and not users:
            raise forms.ValidationError(
                "Scanning user is required when status is In progress."
            )
        return cleaned_data
