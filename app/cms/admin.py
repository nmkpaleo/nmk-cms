from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import Locality, FieldSlip, Storage

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

admin.site.register(Locality, LocalityAdmin)
admin.site.register(FieldSlip, FieldSlipAdmin)
admin.site.register(Storage, StorageAdmin)
