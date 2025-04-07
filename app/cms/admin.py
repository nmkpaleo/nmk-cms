from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget, DateWidget
from .models import (
    NatureOfSpecimen, Element, Person, Identification, Taxon,Media, SpecimenGeology, GeologicalContext,
    AccessionReference, Locality, Collection, Accession, AccessionRow, Subject, Comment, FieldSlip, Reference, Storage, User,
    Preparation, PreparationLog, PreparationMaterial, PreparationMedia
)
from .resources import *
import logging

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.timezone import now

# Configure the logger
logging.basicConfig(level=logging.INFO)  # You can adjust the level as needed (DEBUG, WARNING, ERROR, etc.)
logger = logging.getLogger(__name__)  # Creates a logger specific to the current module

# Accession Model
class AccessionAdmin(ImportExportModelAdmin):
    resource_class = AccessionResource
    list_display = ('collection_abbreviation', 'specimen_prefix_abbreviation', 'specimen_no', 'accessioned_by')
    list_filter = ('collection', 'specimen_prefix', 'accessioned_by')
    search_fields = ('specimen_no', 'collection__abbreviation', 'specimen_prefix__abbreviation', 'accessioned_by__username')
    ordering = ('specimen_no', 'specimen_prefix__abbreviation')

    def collection_abbreviation(self, obj):
        return obj.collection.abbreviation if obj.collection else None
    collection_abbreviation.short_description = 'Collection'

    def specimen_prefix_abbreviation(self, obj):
        return obj.specimen_prefix.abbreviation if obj.specimen_prefix else None
    specimen_prefix_abbreviation.short_description = 'Specimen Prefix'

class AccessionReferenceAdmin(ImportExportModelAdmin):
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

class AccessionRowAdmin(ImportExportModelAdmin):
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
class CommentAdmin(admin.ModelAdmin):
    list_display = ('specimen_no', 'comment', 'status', 'subject', 'comment_by')
    search_fields = ('comment', 'comment_by')
    list_filter = ('status', 'subject', 'comment_by')

# Collection Model
class CollectionAdmin(ImportExportModelAdmin):
    resource_class = CollectionResource
    list_display = ('abbreviation', 'description')
    search_fields = ('abbreviation', 'description')

# Element Model
class ElementAdmin(ImportExportModelAdmin):
    resource_class = ElementResource
    list_display = ('parent_element', 'name')
    list_filter = ('parent_element__name',)
    search_fields = ('name', 'parent_element__name')
    ordering = ('name',)

# FieldSlip Model
class FieldSlipAdmin(ImportExportModelAdmin):
    resource_class = FieldSlipResource
    list_display = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality', 'verbatim_taxon', 'verbatim_element')
    search_fields = ('field_number', 'discoverer', 'collector', 'verbatim_locality')
    list_filter = ('verbatim_locality',)
    ordering = ('verbatim_locality', 'field_number')

#  GeologicalContext
class GeologicalContextAdmin(ImportExportModelAdmin):
    list_display = ('geological_context_type', 'unit_name', 'name', 'parent_geological_context')
    search_fields = ('geological_context_type', 'unit_name', 'name')
    list_filter = ('geological_context_type',)
    ordering = ('name',)

# Identification Model
class IdentificationAdmin(ImportExportModelAdmin):
    resource_class = IdentificationResource
    list_display = ('accession_row', 'identification_qualifier', 'verbatim_identification', 'taxon', 'identified_by', 'date_identified', )
    search_fields = ('accession_row__accession__specimen_no', 'verbatim_identification', 'taxon__taxon_name', 'identified_by__last_name')
    list_filter = ('date_identified',)
    ordering = ('accession_row', 'date_identified')

# Locality Model
class LocalityAdmin(ImportExportModelAdmin):
    resource_class = LocalityResource
    list_display = ('abbreviation', 'name')
    search_fields = ('abbreviation', 'name')
    ordering = ('abbreviation', 'name')

# Media
class MediaAdmin(ImportExportModelAdmin):
    list_display = ('file_name', 'type', 'format', 'media_location', 'license', 'rights_holder', "created_by", "created_on")
    readonly_fields = ("created_by", "modified_by", "created_on", "modified_on")
    search_fields = ('file_name', 'type', 'format', 'media_location', 'license', 'rights_holder')
    list_filter = ('type', 'format')
    ordering = ('file_name',)

# NatureOfSpecimen Model
class NatureOfSpecimenAdmin(ImportExportModelAdmin):
    resource_class = NatureOfSpecimenResource
    list_display = ('accession_row', 'element', 'side', 'condition', 'fragments')
    search_fields = ('accession_row__id', 'element__name', 'side', 'condition')
    ordering = ('accession_row', 'element')

# Person Model
class PersonAdmin(ImportExportModelAdmin):
    resource_class = PersonResource
    list_display = ('first_name', 'last_name', 'orcid')
    search_fields = ('first_name', 'last_name', 'orcid')

# Reference Model
class ReferenceAdmin(ImportExportModelAdmin):
    resource_class = ReferenceResource
    list_display = ('citation', 'doi')
    search_fields = ('citation', 'doi')

# SpecimenGeology
class SpecimenGeologyAdmin(ImportExportModelAdmin):
    list_display = ('accession', 'earliest_geological_context', 'latest_geological_context')
    search_fields = ('accession__specimen_prefix',)
    ordering = ('accession',)

# Storage Model
class StorageAdmin(ImportExportModelAdmin):
    resource_class = StorageResource
    list_display = ('area', 'parent_area')
    search_fields = ('area', 'parent_area__area')

# Subject Model
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('subject_name',)
    search_fields = ('subject_name',)
    list_filter = ('subject_name',)

# TaxonAdmin: Customizes the admin interface for the Taxon model
class TaxonAdmin(ImportExportModelAdmin):
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
class UserAdmin(ImportExportModelAdmin):
    resource_class = UserResource
    list_display = ('username', 'first_name', 'last_name', 'email')
    search_fields = ('username', 'first_name', 'last_name', 'email')

class PreparationLogInline(admin.TabularInline):
    """ Inline display of PreparationLog entries within Preparation admin. """
    model = PreparationLog
    extra = 0
    readonly_fields = ("changed_on", "changed_by", "changes")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False  # Prevents adding new log entries manually

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
class PreparationAdmin(admin.ModelAdmin):
    """ Custom admin panel for Preparation model. """
    
    form = PreparationAdminForm
    list_display = ("accession_row", "preparator", "status", "curator", "approval_status", "approval_date", "admin_colored_status")
    list_filter = ("status", "approval_status", "preparator", "curator")
    search_fields = ("accession_row__accession__specimen_no", "preparator__username", "curator__username")
    readonly_fields = ("approval_date", "created_on", "modified_on", "admin_status_info")
    inlines = [PreparationMediaInline, PreparationLogInline]
    
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
class PreparationMaterialAdmin(admin.ModelAdmin):
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
admin.site.register(NatureOfSpecimen, NatureOfSpecimenAdmin)
admin.site.register(Person, PersonAdmin)
admin.site.register(Reference, ReferenceAdmin)
admin.site.register(Storage, StorageAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Taxon, TaxonAdmin)
# User needs to unregister the default User model and register the custom User model
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(Media, MediaAdmin)
admin.site.register(SpecimenGeology, SpecimenGeologyAdmin)
admin.site.register(GeologicalContext, GeologicalContextAdmin)