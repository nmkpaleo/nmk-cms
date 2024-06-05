from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import Locality, Collection, Accession, Subject, Comment, FieldSlip, Storage

class LocalityResource(resources.ModelResource):
    class Meta:
        model = Locality
        fields = ('name', 'abbreviation')

class LocalityAdmin(ImportExportModelAdmin):
    resource_class = LocalityResource
    list_display = ('name', 'abbreviation')
    search_fields = ('name', 'abbreviation')

class FieldSlipResource(resources.ModelResource):
    class Meta:
        model = FieldSlip
        fields = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality', 'verbatim_taxon', 'verbatim_element', 'verbatim_horizon', 'aerial_photo', 'verbatim_latitude', 'verbatim_longitude', 'verbatim_SRS', 'verbatim_coordinate_system', 'verbatim_elevation', 'accession')

class FieldSlipAdmin(ImportExportModelAdmin):
    resource_class = FieldSlipResource
    list_display = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality')
    search_fields = ('field_number', 'discoverer', 'collector', 'verbatim_locality')

class StorageResource(resources.ModelResource):
    class Meta:
        model = Storage
        fields = ('area', 'parent_area')

class StorageAdmin(ImportExportModelAdmin):
    resource_class = StorageResource
    list_display = ('area', 'parent_area')
    search_fields = ('area', 'parent_area__area')

class CollectionResource(resources.ModelResource):
    class Meta:
        model = Collection
        fields = ('abbreviation', 'description')


class CollectionAdmin(ImportExportModelAdmin):
    resource_class = CollectionResource
    list_display = ('abbreviation', 'description')
    search_fields = ('abbreviation', 'description')


class AccessionResource(resources.ModelResource):
    class Meta:
        model = Accession
        fields = ('collection', 'specimen_prefix', 'specimen_no', 'accessioned_by')


class AccessionAdmin(ImportExportModelAdmin):
    resource_class = AccessionResource
    list_display = ('collection__abbreviation','specimen_prefix__abbreviation', 'specimen_no', 'accessioned_by')
    search_fields = ('specimen_prefix__name', 'specimen_no', 'collection__description', 'accessioned_by__username')


class SubjectResource(resources.ModelResource):
    class Meta:
        model = Subject
        fields = ('subject_name',)


class SubjectAdmin(ImportExportModelAdmin):
    resource_class = SubjectResource
    list_display = ('subject_name',)
    search_fields = ('subject_name',)


class CommentResource(resources.ModelResource):
    class Meta:
        model = Comment
        fields = ('accession', 'comment', 'subject', 'response', 'status', 'comment_by')


class CommentAdmin(ImportExportModelAdmin):
    resource_class = CommentResource
    list_display = ('specimen_no', 'comment', 'subject', 'response', 'status', 'comment_by')
    search_fields = ('specimen_no', 'comment', 'subject__subject_name', 'response', 'status', 'comment_by')
    list_filter = ('response', 'status')

admin.site.register(Locality, LocalityAdmin)
admin.site.register(Collection, CollectionAdmin)
admin.site.register(Accession, AccessionAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Comment, CommentAdmin)
admin.site.register(FieldSlip, FieldSlipAdmin)
admin.site.register(Storage, StorageAdmin)