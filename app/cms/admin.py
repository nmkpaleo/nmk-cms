from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import Locality

class LocalityResource(resources.ModelResource):
    class Meta:
        model = Locality
        fields = ('name', 'abbreviation')

class LocalityAdmin(ImportExportModelAdmin):
    resource_class = LocalityResource
    list_display = ('name', 'abbreviation')  # Fields to display in the locality list
    search_fields = ('name', 'abbreviation')  # Fields to search in the admin interface

admin.site.register(Locality, LocalityAdmin)
