from django.db import models
from django.contrib.auth import get_user_model
from django.urls import reverse
from django_userforeignkey.models.fields import UserForeignKey
from django.db.models import UniqueConstraint
from django.contrib.auth.models import User
import os # For file handling in media class
from django.core.exceptions import ValidationError
import string # For generating specimen number
User = get_user_model()

class BaseModel(models.Model):
    created_on = models.DateTimeField(auto_now_add=True, verbose_name="Date Created")
    modified_on = models.DateTimeField(auto_now=True, verbose_name="Date Modified")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
        verbose_name="Created by"
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_modified",
        verbose_name="Modified by"
    )

    class Meta:
        abstract = True
        ordering = ["-created_on"]
        verbose_name = "Base Record"
        verbose_name_plural = "Base Records"


# Locality Model
class Locality(BaseModel):
    abbreviation = models.CharField(max_length=2, help_text="Enter the Abbreviation of the Locality")
    name = models.CharField(max_length=50, help_text="The name of the Locality.")
    
    class Meta:
        ordering = ["name"]

    def get_absolute_url(self):
        return reverse("locality-detail", args=[str(self.id)])

    def __str__(self):
        return self.name


# Collection Model
class Collection(BaseModel):
    abbreviation = models.CharField(max_length=4)
    description = models.CharField(max_length=250)

    def get_absolute_url(self):
        return reverse('collection-detail', args=[str(self.id)])

    def __str__(self):
        return self.description


# Accession Model
class Accession(BaseModel):
    """
    Represents an accessioned specimen linked to a collection and locality.
    """
    collection = models.ForeignKey(
        "Collection",
        on_delete=models.CASCADE,
        help_text="Select the collection this specimen belongs to."
    )
    specimen_prefix = models.ForeignKey(
        "Locality",
        on_delete=models.CASCADE,
        help_text="Select the specimen prefix."
    )
    specimen_no = models.PositiveIntegerField(
        help_text="Enter the specimen number."
    )
    accessioned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who accessioned the specimen."
    )

    TYPE_STATUS_CHOICES = [
        ('Type', 'Type'),
        ('Holotype', 'Holotype'),
        ('Isotype', 'Isotype'),
        ('Lectotype', 'Lectotype'),
        ('Syntype', 'Syntype'),
        ('Isosyntype', 'Isosyntype'),
        ('Paratype', 'Paratype'),
        ('Neotype', 'Neotype'),
        ('Topotype', 'Topotype'),
    ]

    type_status = models.CharField(
        max_length=50,
        choices=TYPE_STATUS_CHOICES,
        null=True,
        blank=True,
        help_text="Select the type status."
    )
    comment = models.TextField(
        null=True,
        blank=True,
        help_text="Additional comments (if any)."
    )
    is_published = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        """
        Auto-updates `is_published` based on related references.
        If references exist, it sets to True. If none exist, it sets to False.
        """
        self.is_published = self.accessionreference_set.exists()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('accession-detail', args=[str(self.id)])

    def __str__(self):
        collection_abbr = self.collection.abbreviation if self.collection else "N/A"
        prefix_abbr = self.specimen_prefix.abbreviation if self.specimen_prefix else "N/A"
        return f"{collection_abbr}-{prefix_abbr} {self.specimen_no}"

    class Meta:
        ordering = ["collection", "specimen_prefix", "specimen_no"]
        verbose_name = "Accession"
        verbose_name_plural = "Accessions"

# Subject Model
class Subject(BaseModel):
    subject_name = models.CharField(max_length=50)

    def get_absolute_url(self):
        return reverse('subject-detail', args=[str(self.id)])

    def __str__(self):
        return self.subject_name


# Comment Model
class Comment(BaseModel):
    specimen_no = models.ForeignKey(Accession, on_delete=models.CASCADE, related_name='comments')
    comment = models.TextField()
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)

    RESPONSE_STATUS = (
        ('N', 'New'),
        ('P', 'Pending'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
        ('C', 'Closed'),
    )
    
    status = models.CharField(max_length=50, choices=RESPONSE_STATUS, help_text="Please select your response")
    response = models.TextField(null=True, blank=True)
    comment_by = models.CharField(max_length=50)

    def get_absolute_url(self):
        return reverse('comment-detail', args=[str(self.id)])

    def __str__(self):
        return self.comment


# FieldSlip Model
class FieldSlip(BaseModel):
    field_number = models.CharField(max_length=100, null=False, blank=False, help_text="Field number assigned to the specimen.")
    discoverer = models.CharField(max_length=255, null=True, blank=True, help_text="Person who discovered the specimen.")
    collector = models.CharField(max_length=255, null=True, blank=True, help_text="Person who collected the specimen.")
    collection_date = models.DateField(null=True, blank=True, help_text="Date the specimen was collected.")
    verbatim_locality = models.CharField(max_length=255, null=True, blank=True, help_text="Original locality description as recorded.")
    verbatim_taxon = models.CharField(max_length=255, null=False, blank=False, help_text="Taxon name as recorded in the field.")
    verbatim_element = models.CharField(max_length=255, null=False, blank=False, help_text="Skeletal element or fossil part recorded in the field.")
    verbatim_horizon = models.CharField(max_length=255, null=True, blank=True, help_text="Geological horizon as recorded in the field.")
    verbatim_method = models.CharField(max_length=255, null=True, blank=True, help_text="Method used for discovery or collection (sieving etc.).")
    aerial_photo = models.CharField(max_length=25, null=True, blank=True, help_text="Aerial photo reference (if applicable).")
    verbatim_latitude = models.CharField(max_length=255, null=True, blank=True, help_text="Latitude as recorded in the field.")
    verbatim_longitude = models.CharField(max_length=255, null=True, blank=True, help_text="Longitude as recorded in the field.")
    verbatim_SRS = models.CharField(max_length=255, null=True, blank=True, help_text="Spatial reference system used in the field.")
    verbatim_coordinate_system = models.CharField(max_length=255, null=True, blank=True, help_text="Coordinate system used in the field (WGS84 etc.).")
    verbatim_elevation = models.CharField(max_length=255, null=True, blank=True, help_text="Elevation as recorded.")

    def get_absolute_url(self):
        return reverse('fieldslip-detail', args=[str(self.id)])

    def __str__(self):
        return self.field_number if self.field_number else "Unnamed Field Slip"

    class Meta:
        ordering = ["field_number"]
        verbose_name = "Field Slip"
        verbose_name_plural = "Field Slips"

# Storage Model
class Storage(BaseModel):
    area = models.CharField(max_length=255, blank=False, null=False)
    parent_area = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)

    def get_absolute_url(self):
        return reverse('storage-detail', args=[str(self.id)])

    def __str__(self):
        return self.area


# Reference Model
class Reference(BaseModel):
    title = models.CharField(max_length=255, blank=False, null=False)
    first_author = models.CharField(max_length=255, blank=False, null=False)
    year = models.CharField(max_length=4, blank=False, null=False)
    journal = models.CharField(max_length=255, blank=True, null=True)
    volume = models.CharField(max_length=10, blank=True, null=True)
    issue = models.CharField(max_length=10, blank=True, null=True)
    pages = models.CharField(max_length=10, blank=True, null=True)
    doi = models.CharField(max_length=255, blank=True, null=True)
    citation = models.TextField(blank=False, null=False)

    def get_absolute_url(self):
        return reverse('reference-detail', args=[str(self.id)])

    def __str__(self):
        return self.citation


class AccessionFieldSlip(BaseModel):
    """
    Links Accession and FieldSlip in a many-to-many relationship.
    """
    accession = models.ForeignKey(
        "Accession",
        on_delete=models.CASCADE,
        related_name="fieldslip_links",
        help_text="Select the accession."
    )
    fieldslip = models.ForeignKey(
        "FieldSlip",
        on_delete=models.CASCADE,
        related_name="accession_links",
        help_text="Select the field slip."
    )
    
    notes = models.TextField(
        null=True,
        blank=True,
        help_text="Additional notes."
    )

    class Meta:
        unique_together = ("accession", "fieldslip")  # Ensures no duplicate relations
        ordering = ["accession", "fieldslip"]
        verbose_name = "Accession-FieldSlip Link"
        verbose_name_plural = "Accession-FieldSlip Links"

    def __str__(self):
        return f"{self.accession} ↔ {self.fieldslip}"

# AccessionReference Model
class AccessionReference(BaseModel):
    accession = models.ForeignKey(Accession, on_delete=models.CASCADE)
    reference = models.ForeignKey(Reference, on_delete=models.CASCADE)
    page = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['accession', 'reference'],
                name='unique_accession_reference'
            )
        ]

    def get_absolute_url(self):
        return reverse('accessionreference-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.accession} - {self.reference} (Page: {self.page or 'N/A'})"

# AccessionRow Model
class AccessionRow(BaseModel):
    accession = models.ForeignKey(Accession, on_delete=models.CASCADE)
    storage = models.ForeignKey(Storage, on_delete=models.SET_NULL, blank=True, null=True)
    specimen_suffix = models.CharField(max_length=25, blank=True, null=True, default='-')

    def get_absolute_url(self):
        return reverse('accessionrow-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.accession}: {self.specimen_suffix}" if self.specimen_suffix else str(self.accession)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['accession', 'specimen_suffix'], name='unique_accession_specimen_suffix')
        ]
        indexes = [
            models.Index(fields=['accession']),
            models.Index(fields=['specimen_suffix']),
        ]

    def clean(self):
        """ Validate specimen_suffix format and uniqueness """
        self.validate_specimen_suffix()
        self.ensure_unique_suffix()

    def validate_specimen_suffix(self):
        """ Ensure the specimen_suffix is valid """
        valid_suffixes = self.generate_valid_suffixes()
        if self.specimen_suffix != '-' and self.specimen_suffix not in valid_suffixes:
            raise ValidationError(
                {'specimen_suffix': f"Invalid specimen_suffix. Must be '-', A-Z, or within AA-FZ range."}
            )

    def ensure_unique_suffix(self):
        """ Ensure the specimen_suffix is unique within the same accession """
        if AccessionRow.objects.filter(accession=self.accession, specimen_suffix=self.specimen_suffix).exclude(id=self.id).exists():
            raise ValidationError({'specimen_suffix': "This specimen_suffix already exists for this accession."})

    def generate_valid_suffixes(self):
        """ Generate all valid specimen_suffix values """
        suffixes = list(string.ascii_uppercase)  # A-Z
        for first in "ABCDEF":  # A to F for the first letter
            for second in string.ascii_uppercase:  # A-Z for the second letter
                suffixes.append(f"{first}{second}")
        return suffixes

    def save(self, *args, **kwargs):
        """ Assign the next available suffix if specimen_suffix is not provided """
        if not self.specimen_suffix or self.specimen_suffix == '-':
            self.specimen_suffix = self.get_next_available_suffix()
        super().save(*args, **kwargs)

    def get_next_available_suffix(self):
        """ Find the next available suffix for this accession """
        existing_suffixes = AccessionRow.objects.filter(accession=self.accession).values_list('specimen_suffix', flat=True)
        valid_suffixes = self.generate_valid_suffixes()
        
        for suffix in valid_suffixes:
            if suffix not in existing_suffixes:
                return suffix
        raise ValidationError({'specimen_suffix': "No more available suffixes for this accession."})

# NatureOfSpecimen Model
class NatureOfSpecimen(BaseModel):
    accession_row = models.ForeignKey(AccessionRow, on_delete=models.CASCADE)
    element = models.ForeignKey('Element', on_delete=models.CASCADE)
    side = models.CharField(max_length=50, blank=True, null=True)
    condition = models.CharField(max_length=255, blank=True, null=True)
    verbatim_element = models.CharField(max_length=255, blank=True, null=True)
    portion = models.CharField(max_length=255, blank=True, null=True)
    fragments = models.IntegerField(default=0)

    def get_absolute_url(self):
        return reverse('natureofspecimen-detail', args=[str(self.id)])

    def __str__(self):
        return f"NatureOfSpecimen for AccessionRow {self.accession_row}"


# Element Model
class Element(BaseModel):
    parent_element = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    name = models.CharField(max_length=255, blank=False, null=False)

    class Meta:
        ordering = ['parent_element__name', 'name']

    def get_absolute_url(self):
        return reverse('element-detail', args=[str(self.id)])

    def __str__(self):
        return self.name


# Person Model
class Person(BaseModel):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    orcid = models.CharField(max_length=255, blank=True, null=True)

    def get_absolute_url(self):
        return reverse('person-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


# Identification Model
class Identification(BaseModel):
    accession_row = models.ForeignKey(AccessionRow, on_delete=models.CASCADE)
    identified_by = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True)
    taxon = models.CharField(max_length=255, blank=True, null=True)
    reference = models.ForeignKey(Reference, on_delete=models.SET_NULL, null=True, blank=True)
    date_identified = models.DateField(null=True, blank=True)
    identification_qualifier = models.CharField(max_length=255, blank=True, null=True)
    verbatim_identification = models.CharField(max_length=255, blank=True, null=True)
    identification_remarks = models.TextField(blank=True, null=True)

    def get_absolute_url(self):
        return reverse('identification-detail', args=[str(self.id)])

    def __str__(self):
        return f"Identification for AccessionRow {self.accession_row}"


# Taxon Model

TAXON_RANK_CHOICES = [
    ('kingdom', 'Kingdom'),
    ('phylum', 'Phylum'),
    ('class', 'Class'),
    ('order', 'Order'),
    ('family', 'Family'),
    ('genus', 'Genus'),
    ('species', 'Species'),
    ('subspecies', 'Subspecies'),
]

class Taxon(BaseModel):
    taxon_rank = models.CharField(max_length=50, choices=TAXON_RANK_CHOICES)
    taxon_name = models.CharField(max_length=50)
    kingdom = models.CharField(max_length=255)
    phylum = models.CharField(max_length=255)
    class_name = models.CharField(max_length=255)
    order = models.CharField(max_length=255)
    superfamily = models.CharField(max_length=255, null=True, blank=True, default="")
    family = models.CharField(max_length=255)
    subfamily = models.CharField(max_length=255, null=True, blank=True, default="")
    tribe = models.CharField(max_length=255, null=True, blank=True, default="")
    genus = models.CharField(max_length=255)
    species = models.CharField(max_length=255)
    infraspecific_epithet = models.CharField(max_length=255, null=True, blank=True)
    scientific_name_authorship = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['class_name', 'order', 'family', 'genus', 'species']
        verbose_name = 'Taxon'
        verbose_name_plural = 'Taxa'
        constraints = [
            models.UniqueConstraint(
                fields=['taxon_rank', 'taxon_name', 'scientific_name_authorship'],
                name='unique_taxon_rank_name_authorship'
            )
        ]

    def clean(self):
        super().clean()
        if not self.family and (self.genus or self.species):
            raise ValidationError("Genus and species must have a family.")
        if not self.genus and self.species:
            raise ValidationError("Species must have a genus.")

    def get_absolute_url(self):
        return reverse('taxon-detail', args=[str(self.id)])

    def __str__(self):
        if self.infraspecific_epithet:
            return f"{self.genus} {self.species} {self.infraspecific_epithet}"
        return f"{self.genus} {self.species}"


class Media(BaseModel):
    # Dropdown choices for 'type' field
    MEDIA_TYPE_CHOICES = [
        ('photo', 'Photo'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('text', 'Text'),
        ('other', 'Other')
    ]
    
    # Dropdown choices for 'format' field
    # Django ImageField accepts image file types that are supported by the Pillow library
    MEDIA_FORMAT_CHOICES = [
        ('jpg', 'JPG'),
        ('jpeg', 'JPEG'),
        ('png', 'PNG'),
        ('gif', 'GIF'),      
        ('bmp', 'BMP'),
    ]

    # Dropdown choices for 'license' field
    LICENSE_CHOICES = [
        ('CC0', 'Public Domain (CC0)'),
        ('CC_BY', 'Creative Commons - Attribution (CC BY)'),
        ('CC_BY_SA', 'Creative Commons - Attribution-ShareAlike (CC BY-SA)'),
        ('CC_BY_NC', 'Creative Commons - Attribution-NonCommercial (CC BY-NC)'),
        ('CC_BY_ND', 'Creative Commons - Attribution-NoDerivatives (CC BY-ND)'),
        ('CC_BY_NC_SA', 'Creative Commons - Attribution-NonCommercial-ShareAlike (CC BY-NC-SA)'),
        ('CC_BY_NC_ND', 'Creative Commons - Attribution-NonCommercial-NoDerivatives (CC BY-NC-ND)'),
        ('GFDL', 'GNU Free Documentation License (GFDL)'),
        ('OGL', 'Open Government License (OGL)'),
        ('RF', 'Royalty-Free (RF)'),
        ('RM', 'Rights-Managed (RM)'),
        ('EDITORIAL', 'Editorial Use Only'),
        ('CUSTOM_ATTRIBUTION', 'Attribution (Custom License)'),
        ('SHAREWARE', 'Shareware/Donationware'),
        ('EULA', 'End-User License Agreement (EULA)'),
     ]
    
    accession = models.ForeignKey('Accession', null=True, blank=True, on_delete=models.CASCADE, related_name='media', help_text="Accession this media belongs to")
    accession_row = models.ForeignKey('AccessionRow', null=True, blank=True, on_delete=models.CASCADE, related_name='media', help_text="Accession row this media belongs to")    
    file_name = models.CharField(max_length=255, null=True, blank=True, help_text="The name of the media file")
    type = models.CharField(max_length=50, null=True, blank=True, choices=MEDIA_TYPE_CHOICES, help_text="Type of the media (e.g., photo, video, etc.)")
    format = models.CharField(max_length=50, null=True, blank=True, choices=MEDIA_FORMAT_CHOICES, help_text="File format of the media (valid_formats are 'jpg', 'jpeg', 'png', 'gif', 'tiff' and 'bmp'")
    media_location = models.ImageField(upload_to='media/')
    license = models.CharField(max_length=30, choices=LICENSE_CHOICES
                               ,default='CC0'  # Default to public domain
                               , help_text="License information for the media file")
    rights_holder = models.CharField(max_length=255, null=True, blank=True, help_text="The individual or organization holding rights to the media")

    def save(self, *args, **kwargs):
        # If a file is uploaded
        if self.media_location:
            # Get the file name without the directory
            self.file_name = os.path.basename(self.media_location.name)
            print(os.path.basename(self.media_location.name))
            # Get the file extension
            self.format = os.path.splitext(self.media_location.name)[1].lower().strip('.')
            print(os.path.splitext(self.media_location.name)[1].lower().strip('.'))       
        # Call the parent save method
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.media_location:
            valid_formats = ['jpg', 'jpeg', 'png', 'gif', 'bmp']
            extension = os.path.splitext(self.media_location.name)[1].lower().strip('.')
            if extension not in valid_formats:
                raise ValidationError(f"Invalid file format: {extension}. Supported formats are: {', '.join(valid_formats)}.")

    def get_absolute_url(self):
        return reverse('media-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.file_name} ({self.type})"

class SpecimenGeology(BaseModel):
    # ForeignKey relationships to Accession and GeologicalContext
    accession = models.ForeignKey(
        'Accession', 
        on_delete=models.CASCADE, 
        related_name='specimen_geologies', 
        help_text="Accession this specimen geology belongs to"
    )
    earliest_geological_context = models.ForeignKey(
        'GeologicalContext', 
        on_delete=models.CASCADE,
        related_name='specimens_with_earliest_context', 
        help_text="Earliest geological context of the specimen"
    )
    latest_geological_context = models.ForeignKey(
        'GeologicalContext', 
        on_delete=models.CASCADE,  # Required field now
        related_name='specimens_with_latest_context', 
        help_text="Latest geological context of the specimen"
    )    

    class Meta:
        verbose_name = "Specimen Geology"
        verbose_name_plural = "Specimen Geologies"
        ordering = ['accession']
        indexes = [
            models.Index(fields=['accession']),
            models.Index(fields=['earliest_geological_context']),
            models.Index(fields=['latest_geological_context']),
        ]

    def get_absolute_url(self):
        return reverse('specimen-geology-detail', args=[str(self.id)])

    def __str__(self):  
        return f"SpecimenGeology for Accession {self.accession}"

class GeologicalContext(BaseModel):
    # ForeignKey to self for hierarchical relationship (parent-child)
    parent_geological_context = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='child_geological_contexts',
        help_text="Parent geological context (if applicable)"
    )

    
    geological_context_type = models.CharField(max_length=255, help_text="The type of geological context (e.g., Formation, Period, etc.)")
    unit_name = models.CharField(max_length=255, help_text="The name of the geological unit (e.g., stratum, layer, etc.)")
    name = models.CharField(max_length=255, help_text="The name of the geological context (e.g., name of the formation)")

    def get_absolute_url(self):
        return reverse('geologicalcontext-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.name} ({self.unit_name})"