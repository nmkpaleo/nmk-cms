from venv import logger
from .models import Accession, AccessionReference, AccessionRow, Collection, Element, FieldSlip, GeologicalContext, Identification, Locality, Media, NatureOfSpecimen, Person, Reference, SpecimenGeology, Storage, Taxon, User
from import_export import resources, fields
#from import_export.fields import Field
from import_export.widgets import BooleanWidget, ForeignKeyWidget, DateWidget

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
    specimen_no = fields.Field(
        column_name='specimen_no',
        attribute='specimen_no'
    )
    accessioned_by = fields.Field(
        column_name='accessioned_by',
        attribute='accessioned_by',
        widget=ForeignKeyWidget(User, 'username')
    )

    has_duplicates = fields.Field(
        column_name='has_duplicates',
        attribute='has_duplicates',
        widget=BooleanWidget(),
        readonly=True  # 👈 this makes it export-only, not importable
    )

    class Meta:
        model = Accession
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('collection', 'specimen_prefix', 'specimen_no', 'instance_number')
        fields = ('collection', 'specimen_prefix', 'specimen_no',
                  'instance_number', 'accessioned_by', 'accession')
        export_order = ('accession', 'collection', 'specimen_prefix',
                        'specimen_no', 'instance_number',
                        'accessioned_by', 'has_duplicates') # Add 'has_duplicates' to export order

    def dehydrate_accession(self, accession):
        museum = getattr(accession.collection, "abbreviation", "unknown")
        specimen_prefix = getattr(accession.specimen_prefix, "abbreviation", "unknown")
        specimen_no = getattr(accession, "specimen_no", "unknown")
        return '%s-%s %s' % (museum, specimen_prefix, specimen_no)
    
    def dehydrate_has_duplicates(self, obj):
        return Accession.objects.filter(
            specimen_no=obj.specimen_no,
            specimen_prefix=obj.specimen_prefix
        ).count() > 1

class AccessionReferenceResource(resources.ModelResource):
    accession_id= fields.Field(
        column_name='accession',
        attribute='accession',
        widget=ForeignKeyWidget(Accession, 'id')
    )

    collection = fields.Field(
        column_name='collection',
        attribute='accession__collection',
        widget=ForeignKeyWidget(Collection, 'abbreviation')
    )
    specimen_prefix = fields.Field(
        column_name='specimen_prefix',
        attribute='accession__specimen_prefix',
        widget=ForeignKeyWidget(Locality, 'abbreviation')
    )
    specimen_no = fields.Field(
        column_name='specimen_no',
        attribute='accession__specimen_no',
    )
    reference = fields.Field(
        column_name='reference',
        attribute='reference',
        widget=ForeignKeyWidget(Reference, 'citation'),
    )

    page = fields.Field(
        column_name='page',
        attribute='page'
    )

    def before_import(self, dataset, **kwargs):
        # mimic a 'dynamic field' - i.e. append field which exists on
        # model, but not in dataset
        dataset.headers.append("accession")
        super().before_import(dataset, **kwargs)

    def before_import_row(self, row, **kwargs):
        # Add accession_id to the row
        # Validate required fields
        collection = row.get('collection')
        specimen_prefix = row.get('specimen_prefix')
        specimen_no = row.get('specimen_no')
       
        # Raise error if required fields are missing
        if not collection or not specimen_prefix or not specimen_no:
            raise ValueError(
                f"Missing required fields for Accession lookup: collection='{collection}', "
                f"specimen_prefix='{specimen_prefix}', specimen_no='{specimen_no}'."
            )

        # Query Accession model
        accession_queryset = Accession.objects.filter(
            collection__abbreviation=collection,
            specimen_prefix__abbreviation=specimen_prefix,
            specimen_no=specimen_no
        )

        if accession_queryset.count() > 1:
            raise ValueError(
                f"Multiple Accessions found for collection='{collection}', "
                f"specimen_prefix='{specimen_prefix}', specimen_no='{specimen_no}'."
            )

        accession = accession_queryset.first()
        if not accession:
            raise ValueError("Failed to retrieve a valid Accession after query.")
        # Add accession_id to the row
        row['accession'] = str(accession.id)
        print("Import row number: ", kwargs.get('row_number'))
        print(row)

    class Meta:
        model = AccessionReference
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('accession', 'reference',)
        fields = ('accession', 'collection', 'specimen_prefix', 'specimen_no',  'reference', 'page')
        export_order = ('collection', 'specimen_prefix', 'specimen_no',  'reference', 'page')

class AccessionRowResource(resources.ModelResource):
    accession_id= fields.Field(
        column_name='accession',
        attribute='accession',
        widget=ForeignKeyWidget(Accession, 'id')
    )

    collection = fields.Field(
        column_name='collection',
        attribute='accession__collection',
        widget=ForeignKeyWidget(Collection, 'abbreviation')
    )
    specimen_prefix = fields.Field(
        column_name='specimen_prefix',
        attribute='accession__specimen_prefix',
        widget=ForeignKeyWidget(Locality, 'abbreviation')
    )
    specimen_no = fields.Field(
        column_name='specimen_no',
        attribute='accession__specimen_no',
    )
    specimen_suffix = fields.Field(
        column_name='specimen_suffix',
        attribute='specimen_suffix',
    )

    storage = fields.Field(
        column_name='storage',
        attribute='storage',
        widget=ForeignKeyWidget(Storage, 'area'),
    )

    def before_import(self, dataset, **kwargs):
        # mimic a 'dynamic field' - i.e. append field which exists on
        # Mmodel, but not in dataset
        dataset.headers.append("accession")
        dataset.headers.append("kari")
        super().before_import(dataset, **kwargs)

    def before_import_row(self, row, **kwargs):
        # Add accession_id to the row
        # Validate required fields
        collection = row.get('collection')
        specimen_prefix = row.get('specimen_prefix')
        specimen_no = row.get('specimen_no')
        specimen_suffix=row.get('specimen_suffix')
       
        # Raise error if required fields are missing
        if not collection or not specimen_prefix or not specimen_no:
            raise ValueError(
                f"Missing required fields for Accession lookup: collection='{collection}', "
                f"specimen_prefix='{specimen_prefix}', specimen_no='{specimen_no}'."
            )

        # Query Accession model
        accession_queryset = Accession.objects.filter(
            collection__abbreviation=collection,
            specimen_prefix__abbreviation=specimen_prefix,
            specimen_no=specimen_no
        )

        if accession_queryset.count() > 1:
            raise ValueError(
                f"Multiple Accessions found for collection='{collection}', "
                f"specimen_prefix='{specimen_prefix}', specimen_no='{specimen_no}'."
            )

        accession = accession_queryset.first()
        if not accession:
            raise ValueError("Failed to retrieve a valid Accession after query.")
        # Add accession_id to the row
        row['accession'] = str(accession.id)

        row['kari'] = str(int(row.get('accession'))+10)
#        row['accession'] = row.get('kari')
        print("Import row number: ", kwargs.get('row_number'))
        print(row)

    class Meta:
        model = AccessionRow
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('accession_id', 'specimen_suffix',)
        fields = ('accession', 'collection', 'specimen_prefix', 'specimen_no',  'specimen_suffix', 'storage')
        export_order = ('collection', 'specimen_prefix', 'specimen_no',  'specimen_suffix', 'storage')

class CollectionResource(resources.ModelResource):
    class Meta:
        model = Collection
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('abbreviation',)
        fields = ('abbreviation', 'description')
        export_order = ('abbreviation', 'description')

class ElementResource(resources.ModelResource):
    parent_element = fields.Field(
        column_name='parent_element',
        attribute='parent_element',
        widget=ForeignKeyWidget(Element, 'name')
    )
    name = fields.Field(
        column_name='name',
        attribute='name'
    )

    class Meta:
        model = Element
        skip_unchanged = True
        report_skipped = False
        fields = ('parent_element', 'name')  # Fields to import/export
        import_id_fields = ['name']  # Use `name` as the unique identifier


    def before_import_row(self, row, **kwargs):
        """
        Ensures the parent_element exists or creates it if not found.
        """
        parent_name = row.get('parent_element')
        if parent_name:
            # Try to find the parent element by name
            parent_element = Element.objects.filter(name=parent_name).first()
            if not parent_element:
                # Create a new parent element if not found
                parent_element = Element.objects.create(name=parent_name)
            # Update the row with the parent_element's ID
#            row['parent_element'] = parent_element.name
        else:
            # If no parent_element is provided, set it to None
            row['parent_element'] = None

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

class IdentificationResource(resources.ModelResource):
    accession_row_id= fields.Field(
        column_name='accession_row',
        attribute='accession_row',
        widget=ForeignKeyWidget(AccessionRow, 'id')
    )

    collection = fields.Field(
        column_name='collection',
        attribute='accession_row__accession__collection',
        widget=ForeignKeyWidget(Collection, 'abbreviation')
    )
    specimen_prefix = fields.Field(
        column_name='specimen_prefix',
        attribute='accession_row__accession__specimen_prefix',
        widget=ForeignKeyWidget(Locality, 'abbreviation')
    )
    specimen_no = fields.Field(
        column_name='specimen_no',
        attribute='accession_row__accession__specimen_no',
    )
    specimen_suffix = fields.Field(
        column_name='specimen_suffix',
        attribute='accession_row__specimen_suffix',
    )

    identified_by = fields.Field(
        column_name='identified_by',
        attribute='identified_by',
        widget=ForeignKeyWidget(Person, 'last_name'),
    )

    taxon = fields.Field(
        column_name='taxon',
        attribute='taxon',
        widget=ForeignKeyWidget(Taxon, 'taxon_name'),
    )

    reference = fields.Field(
        column_name='reference',
        attribute='reference',
        widget=ForeignKeyWidget(Reference, 'citation'),
    )

    date_identified = fields.Field(
        column_name='date_identified',
        attribute='date_identified',
        widget=DateWidget(format='%Y-%m-%d'),
    )

    identification_qualifier = fields.Field(
        column_name='identification_qualifier',
        attribute='identification_qualifier',
    )

    verbatim_identification = fields.Field(
        column_name='verbatim_identification',
        attribute='verbatim_identification',
    )

    identification_remarks = fields.Field(
        column_name='identification_remarks',
        attribute='identification_remarks',
    )

    def before_import(self, dataset, **kwargs):
        # mimic a 'dynamic field' - i.e. append field which exists on
        # Mmodel, but not in dataset
        dataset.headers.append("accession_row")
        super().before_import(dataset, **kwargs)

    def before_import_row(self, row, **kwargs):
        # Add accession_row_id to the row
        # Validate required fields
        collection = row.get('collection')
        specimen_prefix = row.get('specimen_prefix')
        specimen_no = row.get('specimen_no')
        specimen_suffix=row.get('specimen_suffix')
        date_identified=row.get('date_identified')
        if not date_identified:
            row['date_identified'] = None

        # Raise error if required fields are missing
        if not collection or not specimen_prefix or not specimen_no:
            raise ValueError(
                f"Missing required fields for Accession Row lookup: collection='{collection}', "
                f"specimen_prefix='{specimen_prefix}', specimen_no='{specimen_no}', specimen_suffix='{specimen_suffix}'."
            )

        # Query Accession Row model
        accession_row_queryset = AccessionRow.objects.filter(
            accession__collection__abbreviation=collection,
            accession__specimen_prefix__abbreviation=specimen_prefix,
            accession__specimen_no=specimen_no,
			specimen_suffix=specimen_suffix
        )

        if accession_row_queryset.count() > 1:
            raise ValueError(
                f"Multiple Accession Rows found for collection='{collection}', "
                f"specimen_prefix='{specimen_prefix}', specimen_no='{specimen_no}', specimen_suffix='{specimen_suffix}'."
            )

        accession_row = accession_row_queryset.first()
        if not accession_row:
            raise ValueError("Failed to retrieve a valid Accession Row after query.")
        # Add accession_row_id to the row
        row['accession_row'] = str(accession_row.id)
        print("Import row number: ", kwargs.get('row_number'))
        print(row)

    class Meta:
        model = Identification
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('accession_row_id',)
        fields = ('accession_row', 'collection', 'specimen_prefix', 'specimen_no', 'specimen_suffix', 'identified_by', 'taxon', 'reference', 'date_identified', 'identification_qualifier', 'verbatim_identification', 'identification_remarks')
        export_order = ('collection', 'specimen_prefix', 'specimen_no', 'specimen_suffix', 'identified_by', 'taxon', 'reference', 'date_identified', 'identification_qualifier', 'verbatim_identification', 'identification_remarks')

class LocalityResource(resources.ModelResource):
    class Meta:
        model = Locality
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('abbreviation',)
        fields = ('name', 'abbreviation')
        export_order = ('abbreviation', 'name')

class NatureOfSpecimenResource(resources.ModelResource):
    accession_row_id= fields.Field(
        column_name='accession_row',
        attribute='accession_row',
        widget=ForeignKeyWidget(AccessionRow, 'id')
    )

    collection = fields.Field(
        column_name='collection',
        attribute='accession_row__accession__collection',
        widget=ForeignKeyWidget(Collection, 'abbreviation')
    )
    specimen_prefix = fields.Field(
        column_name='specimen_prefix',
        attribute='accession_row__accession__specimen_prefix',
        widget=ForeignKeyWidget(Locality, 'abbreviation')
    )
    specimen_no = fields.Field(
        column_name='specimen_no',
        attribute='accession_row__accession__specimen_no',
    )
    specimen_suffix = fields.Field(
        column_name='specimen_suffix',
        attribute='accession_row__specimen_suffix',
    )

    element = fields.Field(
        column_name='element',
        attribute='element',
        widget=ForeignKeyWidget(Element, 'name'),
    )

    side = fields.Field(
        column_name='side',
        attribute='side',
    )

    condition = fields.Field(
        column_name='condition',
        attribute='condition',
    )

    verbatim_element = fields.Field(
        column_name='verbatim_element',
        attribute='verbatim_element',
    )

    portion = fields.Field(
        column_name='portion',
        attribute='portion',
    )

    fragments = fields.Field(
        column_name='fragments',
        attribute='fragments',
    )

    def before_import(self, dataset, **kwargs):
        # mimic a 'dynamic field' - i.e. append field which exists on
        # Mmodel, but not in dataset
        dataset.headers.append("accession_row")
        super().before_import(dataset, **kwargs)

    def before_import_row(self, row, **kwargs):
        # Add accession_row_id to the row
        # Validate required fields
        collection = row.get('collection')
        specimen_prefix = row.get('specimen_prefix')
        specimen_no = row.get('specimen_no')
        specimen_suffix=row.get('specimen_suffix')
       
        # Raise error if required fields are missing
        if not collection or not specimen_prefix or not specimen_no:
            raise ValueError(
                f"Missing required fields for Accession Row lookup: collection='{collection}', "
                f"specimen_prefix='{specimen_prefix}', specimen_no='{specimen_no}', specimen_suffix='{specimen_suffix}'."
            )

        # Query Accession Row model
        accession_row_queryset = AccessionRow.objects.filter(
            accession__collection__abbreviation=collection,
            accession__specimen_prefix__abbreviation=specimen_prefix,
            accession__specimen_no=specimen_no,
			specimen_suffix=specimen_suffix
        )

        if accession_row_queryset.count() > 1:
            raise ValueError(
                f"Multiple Accession Rows found for collection='{collection}', "
                f"specimen_prefix='{specimen_prefix}', specimen_no='{specimen_no}', specimen_suffix='{specimen_suffix}'."
            )

        accession_row = accession_row_queryset.first()
        if not accession_row:
            raise ValueError("Failed to retrieve a valid Accession Row after query.")
        # Add accession_row_id to the row
        row['accession_row'] = str(accession_row.id)
        print("Import row number: ", kwargs.get('row_number'))
        print(row)

    class Meta:
        model = NatureOfSpecimen
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('accession_row_id',)
        fields = ('accession_row', 'collection', 'specimen_prefix', 'specimen_no', 'specimen_suffix', 'element', 'side', 'condition', 'verbatim_element', 'portion', 'fragments')
        export_order = ('collection', 'specimen_prefix', 'specimen_no', 'specimen_suffix', 'element', 'side', 'condition', 'verbatim_element', 'portion', 'fragments')

class PersonResource(resources.ModelResource):
    class Meta:
        model = Person
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('first_name', 'last_name',)
        fields = ('first_name', 'last_name', 'orcid')
        export_order = ('first_name', 'last_name', 'orcid')

class ReferenceResource(resources.ModelResource):
    class Meta:
        model = Reference
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('citation',)
        fields = ('title', 'first_author', 'year', 'journal', 'volume', 'issue', 'pages', 'doi', 'citation')
        export_order = ('title', 'first_author', 'year', 'journal', 'volume', 'issue', 'pages', 'doi', 'citation')

class StorageResource(resources.ModelResource):
    class Meta:
        model = Storage
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('area',)
        fields = ('area', 'parent_area')

class TaxonResource(resources.ModelResource):
    # Custom fields can be added or mapped if needed
    genus = fields.Field(attribute='genus', column_name='Genus Name')
    class Meta:
        model = Taxon
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('taxon_name', 'taxon_rank',)
        fields = ('taxon_name', 'taxon_rank', 'kingdom', 'phylum', 'class_name', 'order', 'superfamily', 'family', 'subfamily', 'tribe', 'genus', 'species', 'infraspecific_epithet', 'scientific_name_authorship')
        export_order = ('taxon_name', 'taxon_rank', 'kingdom', 'phylum', 'class_name', 'order', 'superfamily', 'family', 'subfamily', 'tribe', 'genus', 'species', 'infraspecific_epithet', 'scientific_name_authorship')

    def clean_species(self, value):
        if not value.isalpha():
            raise ValueError("Species names must only contain alphabetic characters.")
        return value

class UserResource(resources.ModelResource):
    class Meta:
        model = User
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('username',)
        fields = ('id', 'username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'is_superuser', 'last_login', 'date_joined')
        export_order = ('id', 'username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'is_superuser', 'last_login', 'date_joined')




class MediaResource(resources.ModelResource):
    accession = fields.Field(
        column_name='accession',
        attribute='accession',
        widget=ForeignKeyWidget(Accession, 'id')
    )
    accession_row = fields.Field(
        column_name='accession_row',
        attribute='accession_row',
        widget=ForeignKeyWidget(AccessionRow, 'id')
    )

    class Meta:
        model = Media
        fields = ('id', 'file_name', 'type', 'format', 'media_location', 'license', 'rights_holder', 'accession', 'accession_row')
        export_order = ('id', 'file_name', 'type', 'format', 'media_location', 'license', 'rights_holder', 'accession', 'accession_row')

class SpecimenGeologyResource(resources.ModelResource):
    accession = fields.Field(
        column_name='accession',
        attribute='accession',
        widget=ForeignKeyWidget(Accession, 'id')
    )
    earliest_geological_context = fields.Field(
        column_name='earliest_geological_context',
        attribute='earliest_geological_context',
        widget=ForeignKeyWidget(GeologicalContext, 'id')
    )
    latest_geological_context = fields.Field(
        column_name='latest_geological_context',
        attribute='latest_geological_context',
        widget=ForeignKeyWidget(GeologicalContext, 'id')
    )

    class Meta:
        model = SpecimenGeology
        fields = ('id', 'accession', 'earliest_geological_context', 'latest_geological_context', 'geological_context_type')
        export_order = ('id', 'accession', 'earliest_geological_context', 'latest_geological_context', 'geological_context_type')

class GeologicalContextResource(resources.ModelResource):
    parent_geological_context = fields.Field(
        column_name='parent_geological_context',
        attribute='parent_geological_context',
        widget=ForeignKeyWidget(GeologicalContext, 'id')
    )

    class Meta:
        model = GeologicalContext
        fields = ('id', 'geological_context_type', 'unit_name', 'name', 'parent_geological_context')
        export_order = ('id', 'geological_context_type', 'unit_name', 'name', 'parent_geological_context')