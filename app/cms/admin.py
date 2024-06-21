from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from .models import Locality, Collection, Accession, Subject, Comment, FieldSlip, Storage, User
from import_export.widgets import DateWidget

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
        fields = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality', 'verbatim_taxon', 'verbatim_element', 'verbatim_horizon', 'aerial_photo', 'verbatim_latitude', 'verbatim_longitude', 'verbatim_SRS', 'verbatim_coordinate_system', 'verbatim_elevation', 'accession')

class FieldSlipAdmin(ImportExportModelAdmin):
    resource_class = FieldSlipResource
    list_display = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality')
    search_fields = ('field_number', 'discoverer', 'collector', 'verbatim_locality')

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
        import_id_fields = ('collection', 'specimen_prefix', 'specimen_no', 'accessioned_by')
        fields = ('id', 'collection', 'specimen_prefix', 'specimen_no', 'accessioned_by', 'accession')
        export_order = ('accession', 'collection', 'specimen_prefix', 'specimen_no', 'accessioned_by', 'id')

class AccessionAdmin(ImportExportModelAdmin):
    resource_class = AccessionResource
    list_display = ('collection__abbreviation', 'specimen_prefix__abbreviation', 'specimen_no', 'accessioned_by')
    list_filter = ('collection', 'specimen_prefix', 'accessioned_by')
    search_fields = ('specimen_no', 'collection__abbreviation', 'specimen_prefix__abbreviation', 'accessioned_by__username')

    def collection__abbreviation(self, obj):
        return obj.collection.abbreviation

    collection__abbreviation.short_description = 'Collection'

    def specimen_prefix__abbreviation(self, obj):
        return obj.specimen_prefix.abbreviation

    specimen_prefix__abbreviation.short_description = 'Specimen Prefix'

class CommentAdmin(admin.ModelAdmin):
    list_display = ('specimen_no', 'comment', 'status', 'subject')
    search_fields = ('comment', 'comment_by')
    list_filter = ('status', 'subject', 'comment_by')

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

admin.site.register(Locality, LocalityAdmin)
admin.site.register(Collection)
admin.site.register(Accession, AccessionAdmin)
admin.site.register(Subject)
admin.site.register(Comment, CommentAdmin)
admin.site.register(FieldSlip, FieldSlipAdmin)
admin.site.register(Storage, StorageAdmin)
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

