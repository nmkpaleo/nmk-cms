from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import Locality, Collection, Accession, Subject, Comment


class LocalityResource(resources.ModelResource):
    class Meta:
        model = Locality
        fields = ('name', 'abbreviation')

class LocalityAdmin(ImportExportModelAdmin):
    resource_class = LocalityResource
    list_display = ('name', 'abbreviation')  # Fields to display in the locality list
    search_fields = ('name', 'abbreviation')  # Fields to search in the admin interface

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
        fields = ('collection', 'specimen_prefix', 'specimen_no', 'accessioned_by', 'nature_specimen')


class AccessionAdmin(ImportExportModelAdmin):
    resource_class = AccessionResource
    list_display = ('specimen_prefix', 'specimen_no', 'collection', 'accessioned_by', 'nature_specimen')
    search_fields = ('specimen_prefix__name', 'specimen_no', 'collection__description', 'accessioned_by__username', 'nature_specimen')


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
    list_display = ('accession', 'comment', 'subject', 'response', 'status', 'comment_by')
    search_fields = ('accession__specimen_no', 'comment', 'subject__subject_name', 'response', 'status', 'comment_by')
    list_filter = ('response', 'status')

admin.site.register(Locality, LocalityAdmin)
admin.site.register(Collection, CollectionAdmin)
admin.site.register(Accession, AccessionAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Comment, CommentAdmin)