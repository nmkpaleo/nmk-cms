from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, DateWidget
from .models import (
    NatureOfSpecimen, Element, Person, Identification, Taxon,
    AccessionReference, Locality, Collection, Accession, Subject, Comment, FieldSlip, Reference, Storage, User
)

# Locality Model
class LocalityResource(resources.ModelResource):
    class Meta:
        model = Locality
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('abbreviation',)
        fields = ('name', 'abbreviation')
        export_order = ('abbreviation', 'name')

class LocalityAdmin(ImportExportModelAdmin):
    resource_class = LocalityResource
    list_display = ('abbreviation', 'name')
    search_fields = ('abbreviation', 'name')
    ordering = ('abbreviation', 'name')


# FieldSlip Model
class FieldSlipResource(resources.ModelResource):
    collection_date = fields.Field(
        column_name='collection_date',
        attribute='collection_date',
        widget=DateWidget(format='%d/%m/%Y')
    )

    class Meta:
        model = FieldSlip
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('field_number', 'verbatim_locality')
        fields = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality', 'verbatim_taxon', 'verbatim_element', 'verbatim_horizon', 'aerial_photo', 'verbatim_latitude', 'verbatim_longitude', 'verbatim_SRS', 'verbatim_coordinate_system', 'verbatim_elevation', 'verbatim_method')

class FieldSlipAdmin(ImportExportModelAdmin):
    resource_class = FieldSlipResource
    list_display = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality', 'verbatim_taxon', 'verbatim_element')
    search_fields = ('field_number', 'discoverer', 'collector', 'verbatim_locality')
    list_filter = ('verbatim_locality',)
    ordering = ('verbatim_locality', 'field_number',)


# Storage Model
class StorageResource(resources.ModelResource):
    class Meta:
        model = Storage
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('area',)
        fields = ('area', 'parent_area')

class StorageAdmin(ImportExportModelAdmin):
    resource_class = StorageResource
    list_display = ('area', 'parent_area')
    search_fields = ('area', 'parent_area__area')


# Accession Model
class AccessionResource(resources.ModelResource):
    accession = fields.Field()
    collection = fields.Field(
        column_name='collection',
        attribute='collection',
        widget=ForeignKeyWidget(Collection, 'abbreviation')
    )
    specimen_prefix = fields.Field(
        column_name='specimen_prefix',
        attribute='specimen_prefix',
        widget=ForeignKeyWidget(Locality, 'abbreviation')
    )
    accessioned_by = fields.Field(
        column_name='accessioned_by',
        attribute='accessioned_by',
        widget=ForeignKeyWidget(User, 'username')
    )

    def dehydrate_accession(self, accession):
        museum = getattr(accession.collection, "abbreviation", "unknown")
        specimen_prefix = getattr(accession.specimen_prefix, "abbreviation", "unknown")
        specimen_no = getattr(accession, "specimen_no", "unknown")
        return '%s-%s %s' % (museum, specimen_prefix, specimen_no)
    
    class Meta:
        model = Accession
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('collection', 'specimen_prefix', 'specimen_no',)
        fields = ('id', 'collection', 'specimen_prefix', 'specimen_no', 'accessioned_by', 'accession')
        export_order = ('accession', 'collection', 'specimen_prefix', 'specimen_no', 'accessioned_by', 'id')

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


# Comment Model
class CommentAdmin(admin.ModelAdmin):
    list_display = ('specimen_no', 'comment', 'status', 'subject')
    search_fields = ('comment', 'comment_by')
    list_filter = ('status', 'subject', 'comment_by')


# User Model
class UserResource(resources.ModelResource):
    class Meta:
        model = User
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('username',)
        fields = ('id', 'username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'is_superuser', 'last_login', 'date_joined')
        export_order = ('id', 'username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'is_superuser', 'last_login', 'date_joined')

class UserAdmin(ImportExportModelAdmin):
    resource_class = UserResource
    list_display = ('username', 'first_name', 'last_name', 'email')
    search_fields = ('username', 'first_name', 'last_name', 'email')


# Collection Model
class CollectionResource(resources.ModelResource):
    class Meta:
        model = Collection
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('abbreviation',)
        fields = ('abbreviation', 'description')
        export_order = ('abbreviation', 'description')

class CollectionAdmin(ImportExportModelAdmin):
    resource_class = CollectionResource
    list_display = ('abbreviation', 'description')
    search_fields = ('abbreviation', 'description')


# NatureOfSpecimen Model
class NatureOfSpecimenResource(resources.ModelResource):
    accession_row = fields.Field(
        column_name='accession_row',
        attribute='accession_row',
        widget=ForeignKeyWidget(Accession, 'id')
    )
    element = fields.Field(
        column_name='element',
        attribute='element',
        widget=ForeignKeyWidget(Element, 'id')
    )

    class Meta:
        model = NatureOfSpecimen
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('accession_row', 'element',)
        fields = ('accession_row', 'element', 'side', 'condition', 'verbatim_element', 'portion', 'fragments')
        export_order = ('accession_row', 'element', 'side', 'condition', 'verbatim_element', 'portion', 'fragments')

class NatureOfSpecimenAdmin(ImportExportModelAdmin):
    resource_class = NatureOfSpecimenResource
    list_display = ('accession_row', 'element', 'side', 'condition', 'fragments')
    search_fields = ('accession_row__id', 'element__name', 'side', 'condition')
    ordering = ('accession_row', 'element')


# Element Model
class ElementResource(resources.ModelResource):
    parent_element = fields.Field(
        column_name='parent_element',
        attribute='parent_element',
        widget=ForeignKeyWidget(Element, 'id')
    )

    class Meta:
        model = Element
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('name',)
        fields = ('name', 'parent_element')
        export_order = ('name', 'parent_element')

class ElementAdmin(ImportExportModelAdmin):
    resource_class = ElementResource
    list_display = ('name', 'parent_element')
    search_fields = ('name', 'parent_element__name')
    ordering = ('name',)


# Person Model
class PersonResource(resources.ModelResource):
    class Meta:
        model = Person
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('first_name', 'last_name',)
        fields = ('first_name', 'last_name', 'orcid')
        export_order = ('first_name', 'last_name', 'orcid')

class PersonAdmin(ImportExportModelAdmin):
    resource_class = PersonResource
    list_display = ('first_name', 'last_name', 'orcid')
    search_fields = ('first_name', 'last_name', 'orcid')
    ordering = ('last_name', 'first_name')


# Identification Model
class IdentificationResource(resources.ModelResource):
    accession_row = fields.Field(
        column_name='accession_row',
        attribute='accession_row',
        widget=ForeignKeyWidget(Accession, 'id')
    )
    identified_by = fields.Field(
        column_name='identified_by',
        attribute='identified_by',
        widget=ForeignKeyWidget(Person, 'id')
    )
    taxon = fields.Field(
        column_name='taxon',
        attribute='taxon',
        widget=ForeignKeyWidget(Taxon, 'id')
    )
    reference = fields.Field(
        column_name='reference',
        attribute='reference',
        widget=ForeignKeyWidget(Reference, 'id')
    )

    class Meta:
        model = Identification
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('accession_row', 'identified_by', 'taxon',)
        fields = ('accession_row', 'identified_by', 'taxon', 'reference', 'date_identified', 'identification_qualifier', 'verbatim_identification', 'identification_remarks')
        export_order = ('accession_row', 'identified_by', 'taxon', 'reference', 'date_identified', 'identification_qualifier', 'verbatim_identification', 'identification_remarks')

class IdentificationAdmin(ImportExportModelAdmin):
    resource_class = IdentificationResource
    list_display = ('accession_row', 'identified_by', 'taxon', 'date_identified', 'identification_qualifier')
    search_fields = ('accession_row__id', 'identified_by__first_name', 'identified_by__last_name', 'taxon__genus', 'taxon__species')
    ordering = ('accession_row', 'identified_by')


# Taxon Model
class TaxonResource(resources.ModelResource):
    class Meta:
        model = Taxon
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('genus', 'species',)
        fields = ('taxon_rank', 'kingdom', 'phylum', 'class_name', 'order', 'superfamily', 'family', 'subfamily', 'tribe', 'genus', 'species', 'infraspecific_epithet', 'scientific_name_authorship')
        export_order = ('taxon_rank', 'kingdom', 'phylum', 'class_name', 'order', 'superfamily', 'family', 'subfamily', 'tribe', 'genus', 'species', 'infraspecific_epithet', 'scientific_name_authorship')

class TaxonAdmin(ImportExportModelAdmin):
    resource_class = TaxonResource
    list_display = ('genus', 'species', 'kingdom', 'phylum', 'class_name', 'order', 'family')
    search_fields = ('genus', 'species', 'family')
    ordering = ('genus', 'species')


# Register models
admin.site.register(Locality, LocalityAdmin)
admin.site.register(Collection, CollectionAdmin)
admin.site.register(Accession, AccessionAdmin)
admin.site.register(Subject)
admin.site.register(Comment, CommentAdmin)
admin.site.register(FieldSlip, FieldSlipAdmin)
admin.site.register(Storage, StorageAdmin)
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(NatureOfSpecimen, NatureOfSpecimenAdmin)
admin.site.register(Element, ElementAdmin)
admin.site.register(Person, PersonAdmin)
admin.site.register(Identification, IdentificationAdmin)
admin.site.register(Taxon, TaxonAdmin)
