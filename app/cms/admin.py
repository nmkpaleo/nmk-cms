from django.contrib import admin
from django.db.models import Count, OuterRef, Exists

from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget, DateWidget
from simple_history.admin import SimpleHistoryAdmin

from .forms import AccessionNumberSeriesAdminForm, DrawerRegisterForm

from .models import (
    AccessionNumberSeries,
    NatureOfSpecimen,
    Element,
    Person,
    Identification,
    Taxon,
    Media,
    SpecimenGeology,
    GeologicalContext,
    AccessionReference,
    Locality,
    Place,
    Collection,
    Accession,
    AccessionRow,
    Subject,
    Comment,
    FieldSlip,
    Reference,
    Storage,
    User,
    Preparation,
    PreparationMaterial,
    PreparationMedia,
    DrawerRegister,
    Scanning,
    UnexpectedSpecimen,
)
from .resources import *

import json
import logging

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.timezone import now
from django.contrib.auth import get_user_model

# Configure the logger
logging.basicConfig(level=logging.INFO)  # You can adjust the level as needed (DEBUG, WARNING, ERROR, etc.)
logger = logging.getLogger(__name__)  # Creates a logger specific to the current module

from django.contrib import admin
from django.db.models import Count, OuterRef, Exists
from cms.models import Accession

User = get_user_model()


class HistoricalImportExportAdmin(SimpleHistoryAdmin, ImportExportModelAdmin):
    """Base admin class combining simple history and import-export."""
    pass


class HistoricalAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    """Base admin class for models using simple history."""
    pass

class DuplicateFilter(admin.SimpleListFilter):
    title = 'By Duplicate specimen_no + prefix'
    parameter_name = 'duplicates'

    def lookups(self, request, model_admin):
        return [
            ('yes', 'Yes – Show Duplicates'),
            ('no', 'No – Show Unique Only'),
        ]

    def queryset(self, request, queryset):
        duplicate_subquery = (
            Accession.objects
            .filter(
                specimen_no=OuterRef('specimen_no'),
                specimen_prefix=OuterRef('specimen_prefix')
            )
            .values('specimen_no', 'specimen_prefix')
            .annotate(dups=Count('id'))
            .filter(dups__gt=1)
        )

        # Always annotate
        annotated = queryset.annotate(
            has_duplicates=Exists(duplicate_subquery)
        )

        if self.value() == 'yes':
            return annotated.filter(has_duplicates=True)
        elif self.value() == 'no':
            return annotated.filter(has_duplicates=False)
        else:
            return annotated  # ✅ return the annotated base queryset

# Accession Model
class AccessionAdmin(HistoricalImportExportAdmin):
    resource_class = AccessionResource
    list_display = ('collection_abbreviation', 'specimen_prefix_abbreviation',
                    'specimen_no', 'instance_number','accessioned_by',
                    'is_duplicate_display',)
    list_filter = ('collection', 'specimen_prefix', 'accessioned_by', DuplicateFilter)
    search_fields = ('specimen_no', 'collection__abbreviation', 'specimen_prefix__abbreviation', 'accessioned_by__username')
    ordering = ('specimen_no', 'specimen_prefix__abbreviation')

    def collection_abbreviation(self, obj):
        return obj.collection.abbreviation if obj.collection else None
    collection_abbreviation.short_description = 'Collection'

    def specimen_prefix_abbreviation(self, obj):
        return obj.specimen_prefix.abbreviation if obj.specimen_prefix else None
    specimen_prefix_abbreviation.short_description = 'Specimen Prefix'

    def is_duplicate_display(self, obj):
        count = Accession.objects.filter(
            specimen_no=obj.specimen_no,
            specimen_prefix=obj.specimen_prefix
        ).count()
        if count > 1:
            return format_html('<span style="color: orange;">Yes ({})</span>', count)
        return format_html('<span style="color: green;">No</span>')
    is_duplicate_display.short_description = 'Duplicate?'


@admin.register(AccessionNumberSeries)
class AccessionNumberSeriesAdmin(HistoricalAdmin):
    form = AccessionNumberSeriesAdminForm
    change_form_template = "admin/cms/accessionnumberseries/change_form.html"
    list_display = ('user', 'start_from', 'end_at', 'current_number', 'is_active')
    list_filter = ('is_active', 'user')

    fieldsets = (
        (None, {
            'fields': ('user', 'start_from', 'current_number', 'count', 'is_active')
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return [f.name for f in self.model._meta.fields if f.editable and f.name != "id"] + ['count']
        return super().get_readonly_fields(request, obj)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['add'] = object_id is None  # True if adding
        return super().changeform_view(request, object_id, form_url, extra_context=extra_context)

    class Media:
        js = (
            "js/set_start_from.js",
            "js/accession_series_live_preview.js",
        )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)

        if db_field.name == "user":
            # Compute shared vs Mary series
            from django.contrib.auth import get_user_model
            User = get_user_model()

        try:
            mary_series = AccessionNumberSeries.objects.filter(user__username__iexact="mary")
            shared_series = AccessionNumberSeries.objects.exclude(user__username__iexact="mary")

            mary_end = mary_series.order_by('-end_at').first()
            shared_end = shared_series.order_by('-end_at').first()

            series_map = {
                "mary": mary_end.end_at + 1 if mary_end and mary_end.end_at else 1_000_000,
                "shared": shared_end.end_at + 1 if shared_end and shared_end.end_at else 1,
            }

            if hasattr(formfield.widget, 'attrs'):
                formfield.widget.attrs["data-series-starts"] = json.dumps(series_map)

        except Exception as e:
            # Just log the issue, don't block the form rendering or validation
            import logging
            logging.warning(f"Series mapping failed: {e}")

        return formfield

class AccessionReferenceAdmin(HistoricalImportExportAdmin):
    resource_class = AccessionReferenceResource
    list_display = ('collection_abbreviation', 'specimen_prefix_abbreviation', 'specimen_number', 'page', 'reference')
    search_fields = ('accession__specimen_no', 'specimen_suffix', 'reference',)
    ordering = ('accession__collection__abbreviation', 'accession__specimen_prefix__abbreviation', 'accession__specimen_no',)

    def collection_abbreviation(self, obj):
        return obj.accession.collection.abbreviation if obj.accession.collection else None
    collection_abbreviation.short_description = 'Collection'

    def specimen_prefix_abbreviation(self, obj):
        return obj.accession.specimen_prefix.abbreviation if obj.accession.specimen_prefix else None
    specimen_prefix_abbreviation.short_description = 'Specimen Prefix'

    def specimen_number(self, obj):
        return obj.accession.specimen_no if obj.accession.specimen_no else None
    specimen_number.short_description = 'Specimen Number'

class AccessionRowAdmin(HistoricalImportExportAdmin):
    resource_class = AccessionRowResource
    list_display = ('collection_abbreviation', 'specimen_prefix_abbreviation', 'specimen_number', 'specimen_suffix', 'storage')
    search_fields = ('accession__specimen_no', 'specimen_suffix', 'storage__area',)
    ordering = ('accession__collection__abbreviation', 'accession__specimen_prefix__abbreviation', 'accession__specimen_no', 'specimen_suffix',)

    def collection_abbreviation(self, obj):
        return obj.accession.collection.abbreviation if obj.accession.collection else None
    collection_abbreviation.short_description = 'Collection'

    def specimen_prefix_abbreviation(self, obj):
        return obj.accession.specimen_prefix.abbreviation if obj.accession.specimen_prefix else None
    specimen_prefix_abbreviation.short_description = 'Specimen Prefix'

    def specimen_number(self, obj):
        return obj.accession.specimen_no if obj.accession.specimen_no else None
    specimen_number.short_description = 'Specimen Number'

# Comment Model
class CommentAdmin(HistoricalAdmin):
    list_display = ('specimen_no', 'comment', 'status', 'subject', 'comment_by')
    search_fields = ('comment', 'comment_by')
    list_filter = ('status', 'subject', 'comment_by')

# Collection Model
class CollectionAdmin(HistoricalImportExportAdmin):
    resource_class = CollectionResource
    list_display = ('abbreviation', 'description')
    search_fields = ('abbreviation', 'description')

# Element Model
class ElementAdmin(HistoricalImportExportAdmin):
    resource_class = ElementResource
    list_display = ('parent_element', 'name')
    list_filter = ('parent_element__name',)
    search_fields = ('name', 'parent_element__name')
    ordering = ('name',)

# FieldSlip Model
class FieldSlipAdmin(HistoricalImportExportAdmin):
    resource_class = FieldSlipResource
    list_display = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality', 'verbatim_taxon', 'verbatim_element')
    search_fields = ('field_number', 'discoverer', 'collector', 'verbatim_locality')
    list_filter = ('verbatim_locality',)
    ordering = ('verbatim_locality', 'field_number')

#  GeologicalContext
class GeologicalContextAdmin(HistoricalImportExportAdmin):
    list_display = ('geological_context_type', 'unit_name', 'name', 'parent_geological_context')
    search_fields = ('geological_context_type', 'unit_name', 'name')
    list_filter = ('geological_context_type',)
    ordering = ('name',)

# Identification Model
class IdentificationAdmin(HistoricalImportExportAdmin):
    resource_class = IdentificationResource
    list_display = ('accession_row', 'identification_qualifier', 'verbatim_identification', 'taxon', 'identified_by', 'date_identified', )
    search_fields = ('accession_row__accession__specimen_no', 'verbatim_identification', 'taxon__taxon_name', 'identified_by__last_name')
    list_filter = ('date_identified',)
    ordering = ('accession_row', 'date_identified')

# Locality Model
class LocalityAdmin(HistoricalImportExportAdmin):
    resource_class = LocalityResource
    list_display = ('abbreviation', 'name')
    search_fields = ('abbreviation', 'name')
    ordering = ('abbreviation', 'name')


class PlaceAdmin(HistoricalImportExportAdmin):
    resource_class = PlaceResource
    list_display = ('name', 'place_type', 'locality', 'relation_type', 'related_place')
    list_filter = ('place_type', 'relation_type', 'locality')
    search_fields = ('name', 'locality__name')

# Media
class MediaAdmin(HistoricalImportExportAdmin):
    list_display = ('file_name', 'type', 'format', 'media_location', 'license', 'rights_holder', "created_by", "created_on")
    readonly_fields = ("created_by", "modified_by", "created_on", "modified_on")
    search_fields = ('file_name', 'type', 'format', 'media_location', 'license', 'rights_holder')
    list_filter = ('type', 'format')
    ordering = ('file_name',)

# NatureOfSpecimen Model
class NatureOfSpecimenAdmin(HistoricalImportExportAdmin):
    resource_class = NatureOfSpecimenResource
    list_display = ('accession_row', 'element', 'side', 'condition', 'fragments')
    search_fields = ('accession_row__id', 'element__name', 'side', 'condition')
    ordering = ('accession_row', 'element')

# Person Model
class PersonAdmin(HistoricalImportExportAdmin):
    resource_class = PersonResource
    list_display = ('first_name', 'last_name', 'orcid')
    search_fields = ('first_name', 'last_name', 'orcid')

# Reference Model
class ReferenceAdmin(HistoricalImportExportAdmin):
    resource_class = ReferenceResource
    list_display = ('citation', 'doi')
    search_fields = ('citation', 'doi')

# SpecimenGeology
class SpecimenGeologyAdmin(HistoricalImportExportAdmin):
    list_display = ('accession', 'earliest_geological_context', 'latest_geological_context')
    search_fields = ('accession__specimen_prefix',)
    ordering = ('accession',)

# Storage Model
class StorageAdmin(HistoricalImportExportAdmin):
    resource_class = StorageResource
    list_display = ('area', 'parent_area')
    search_fields = ('area', 'parent_area__area')

# Subject Model
class SubjectAdmin(HistoricalAdmin):
    list_display = ('subject_name',)
    search_fields = ('subject_name',)
    list_filter = ('subject_name',)

# TaxonAdmin: Customizes the admin interface for the Taxon model
class TaxonAdmin(HistoricalImportExportAdmin):
    resource_class = TaxonResource

    # Columns to display in the admin list view
    list_display = ('taxon_name', 'taxon_rank', 'order', 'family', 'subfamily', 'tribe', 'genus', 'species', 'formatted_subspecies')
    list_filter = ('taxon_rank', 'kingdom', 'phylum', 'class_name', 'order', 'superfamily', 'family')
    ordering = ('taxon_name', 'taxon_rank', 'kingdom', 'phylum', 'class_name', 'order', 'superfamily', 'family', 'subfamily', 'tribe', 'genus', 'species', 'infraspecific_epithet', 'scientific_name_authorship')
    search_fields = ('taxon_name', 'order', 'superfamily', 'family', 'subfamily', 'tribe', 'genus', 'species', 'infraspecific_epithet', 'scientific_name_authorship')

    # Custom method to display the formatted taxon name
    def formatted_name(self, obj):
        return str(obj)  # Calls __str__ method of the Taxon model
    formatted_name.short_description = 'Taxon Name'

    # Custom method to handle subspecies display
    def formatted_subspecies(self, obj):
        return obj.infraspecific_epithet if obj.infraspecific_epithet else "-"
    formatted_subspecies.short_description = 'Subspecies'

# User Model
class UserAdmin(HistoricalImportExportAdmin):
    resource_class = UserResource
    list_display = ('username', 'first_name', 'last_name', 'email')
    search_fields = ('username', 'first_name', 'last_name', 'email')

class PreparationAdminForm(forms.ModelForm):
    """ Custom form for validation and dynamic field handling in admin. """
    
    class Meta:
        model = Preparation
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        preparator = cleaned_data.get("preparator")
        curator = cleaned_data.get("curator")
        status = cleaned_data.get("status")
        approval_status = cleaned_data.get("approval_status")

        # Ensure Curator is different from Preparator
        if preparator and curator and preparator == curator:
            raise ValidationError({"curator": "The curator must be different from the preparator."})

        # Ensure curation is only done for completed preparations
        if approval_status in ["approved", "declined"] and status != "Completed":
            raise ValidationError({"approval_status": "Preparation must be 'Completed' before approval or rejection."})

        return cleaned_data

class PreparationMediaInline(admin.TabularInline):
    model = PreparationMedia
    extra = 1
    autocomplete_fields = ["media"]
    fields = ("media", "context", "notes")


@admin.register(Preparation)
class PreparationAdmin(HistoricalImportExportAdmin):
    """ Custom admin panel for Preparation model. """

    resource_class = PreparationResource
    form = PreparationAdminForm
    list_display = ("accession_row", "preparator", "status", "curator", "approval_status", "approval_date", "admin_colored_status")
    list_filter = ("status", "approval_status", "preparator", "curator")
    search_fields = ("accession_row__accession__specimen_no", "preparator__username", "curator__username")
    readonly_fields = ("approval_date", "created_on", "modified_on", "admin_status_info")
    inlines = [PreparationMediaInline]
    
    fieldsets = (
        ("Preparation Details", {
            "fields": ("accession_row", "preparator", "preparation_type", "reason", "status", "started_on", "completed_on", "notes"),
        }),
        ("Storage & Condition", {
            "fields": ("original_storage", "temporary_storage", "condition_before", "condition_after", "preparation_method", "chemicals_used", "materials_used"),
            "classes": ("collapse",),
        }),
        ("Curation & Approval", {
            "fields": ("curator", "approval_status", "approval_date", "curator_comments"),
            "classes": ("collapse",),
        }),
        ("Audit Info", {
            "fields": ("created_on", "modified_on", "admin_status_info"),
        }),
    )

    def save_model(self, request, obj, form, change):
        """ Custom save logic to track status changes and auto-fill fields. """
        if not obj.preparator:
            obj.preparator = request.user  # Assign current user if no preparator set
        
        if obj.approval_status in ["approved", "declined"] and not obj.approval_date:
            obj.approval_date = now()  # Auto-fill approval date if approved/declined

        super().save_model(request, obj, form, change)

    def admin_colored_status(self, obj):
        """ Displays colored status for better visibility in admin. """
        color_map = {
            "Pending": "orange",
            "In Progress": "blue",
            "Completed": "green",
            "Approved": "darkgreen",
            "Declined": "red",
        }
        return format_html(f'<span style="color: {color_map.get(obj.status, "black")}; font-weight: bold;">{obj.status}</span>')
    
    admin_colored_status.short_description = "Status"

    def admin_status_info(self, obj):
        """ Displays summary of preparation status in admin view. """
        return format_html(
            "<b>Status:</b> {}<br><b>Curator:</b> {}<br><b>Approval Date:</b> {}",
            obj.status,
            obj.curator.username if obj.curator else "Not Assigned",
            obj.approval_date.strftime("%Y-%m-%d %H:%M") if obj.approval_date else "Not Approved",
        )

    admin_status_info.short_description = "Status Overview"

@admin.register(PreparationMaterial)
class PreparationMaterialAdmin(HistoricalImportExportAdmin):
    resource_class = PreparationMaterialResource
    list_display = ("name", "description")
    search_fields = ("name",)

# Register the models with the customized admin interface
admin.site.register(Accession, AccessionAdmin)
admin.site.register(AccessionReference, AccessionReferenceAdmin)
admin.site.register(AccessionRow, AccessionRowAdmin)
admin.site.register(Collection, CollectionAdmin)
admin.site.register(Comment, CommentAdmin)
admin.site.register(Element, ElementAdmin)
admin.site.register(FieldSlip, FieldSlipAdmin)
admin.site.register(Identification, IdentificationAdmin)
admin.site.register(Locality, LocalityAdmin)
admin.site.register(Place, PlaceAdmin)
admin.site.register(NatureOfSpecimen, NatureOfSpecimenAdmin)
admin.site.register(Person, PersonAdmin)
admin.site.register(Reference, ReferenceAdmin)
admin.site.register(Storage, StorageAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Taxon, TaxonAdmin)
# Unregister safely (may already be registered)
if admin.site.is_registered(User):
    admin.site.unregister(User)
# Optional: Register with custom admin if you need to modify
    admin.site.register(User, UserAdmin)
admin.site.register(Media, MediaAdmin)
admin.site.register(SpecimenGeology, SpecimenGeologyAdmin)
admin.site.register(GeologicalContext, GeologicalContextAdmin)
admin.site.register(UnexpectedSpecimen, HistoricalAdmin)


@admin.register(DrawerRegister)
class DrawerRegisterAdmin(HistoricalImportExportAdmin):
    resource_class = DrawerRegisterResource
    form = DrawerRegisterForm
    list_display = ("code", "description", "estimated_documents", "scanning_status")
    list_filter = ("scanning_status",)
    search_fields = ("code", "description")
    filter_horizontal = ("localities", "taxa", "scanning_users")


@admin.register(Scanning)
class ScanningAdmin(admin.ModelAdmin):
    list_display = ("drawer", "user", "start_time", "end_time")
    list_filter = ("user", "drawer")

# ----------------------------------------------------------------------
# Flat file import integration
# ----------------------------------------------------------------------
from django.urls import path
from django.contrib import messages
from django.shortcuts import render, redirect
from django import forms
from .importer import import_flat_file


class FlatImportForm(forms.Form):
    """Simple form for uploading a combined import file."""

    import_file = forms.FileField(label="Import CSV")


def flat_file_import_view(request):
    """Handle the flat file import process."""
    if request.method == "POST":
        form = FlatImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                count = import_flat_file(form.cleaned_data["import_file"])
                messages.success(request, f"Imported {count} rows successfully.")
                return redirect("admin:index")
            except Exception as exc:  # pragma: no cover - best effort
                messages.error(request, f"Import failed: {exc}")
    else:
        form = FlatImportForm()

    context = {"form": form, "title": "Flat File Import"}
    return render(request, "admin/flat_file_import.html", context)


original_get_urls = admin.site.get_urls


def get_urls():
    urls = original_get_urls()
    custom_urls = [
        path(
            "flat-file-import/",
            admin.site.admin_view(flat_file_import_view),
            name="flat-file-import",
        ),
    ]
    return custom_urls + urls


admin.site.get_urls = get_urls
