from import_export import resources
from .models import FieldSlip

class FieldSlipResource(resources.ModelResource):
    class Meta:
        model = FieldSlip
        fields = (
            'field_number',
            'discoverer',
            'collector',
            'collection_date',
            'verbatim_locality',
            'verbatim_taxon',
            'verbatim_element',
            'verbatim_horizon',
            'aerial_photo',
            'verbatim_latitude',
            'verbatim_longitude',
            'verbatim_SRS',
            'verbatim_coordinate_system',
            'verbatim_elevation',
            'verbatim_method',
        )
        import_id_fields = ('field_number',)  # the unique field for import
