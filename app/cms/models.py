from django.db import models
from django.urls import reverse
from django_userforeignkey.models.fields import UserForeignKey
from django.contrib.auth.models import User

class BaseModel(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    created_by = UserForeignKey(
        auto_user_add=True,
        verbose_name="The user that is automatically assigned",
        related_name="%(class)s_createdby",
    )
    modified_by = UserForeignKey(
        auto_user_add=True,
        verbose_name="The user that is automatically assigned",
        related_name="%(class)s_modifiedby",
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


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
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, help_text="Please select the collection")
    specimen_prefix = models.ForeignKey(Locality, on_delete=models.CASCADE, help_text="Please select the specimen prefix")
    specimen_no = models.PositiveIntegerField(help_text="Please enter the specimen number")
    accessioned_by = models.ForeignKey(User, on_delete=models.CASCADE, help_text="Please select the user who accessioned the specimen")

    options = (
        ('Type', 'Type'),
        ('Holotype', 'Holotype'),
        ('Isotype', 'Isotype'),
        ('Lectotype', 'Lectotype'),
        ('Syntype', 'Syntype'),
        ('Isosyntype', 'Isosyntype'),
        ('Paratype', 'Paratype'),
        ('Neotype', 'Neotype'),
        ('Topotype', 'Topotype'),
    )
    
    type_status = models.CharField(max_length=50, choices=options, null=True, blank=True, help_text="Please select the type status")
    comment = models.TextField(null=True, blank=True, help_text="Any additional comments")

    def get_absolute_url(self):
        return reverse('accession-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.collection.abbreviation}-{self.specimen_prefix.abbreviation} {self.specimen_no}"


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
    field_number = models.CharField(max_length=100)
    discoverer = models.CharField(max_length=255, null=True, blank=True)
    collector = models.CharField(max_length=255, null=True, blank=True)
    collection_date = models.DateField(null=True, blank=True)
    verbatim_locality = models.CharField(max_length=255, null=True, blank=True)
    verbatim_taxon = models.CharField(max_length=255, null=True, blank=True)
    verbatim_element = models.CharField(max_length=255, null=True, blank=True)
    verbatim_horizon = models.CharField(max_length=255, null=True, blank=True)
    verbatim_method = models.CharField(max_length=255, null=True, blank=True)
    
    aerial_photo = models.ImageField(upload_to='aerial_photos/', null=True, blank=True)

    verbatim_latitude = models.CharField(max_length=255, null=True, blank=True)
    verbatim_longitude = models.CharField(max_length=255, null=True, blank=True)
    verbatim_SRS = models.CharField(max_length=255, null=True, blank=True)
    verbatim_coordinate_system = models.CharField(max_length=255, null=True, blank=True)
    verbatim_elevation = models.CharField(max_length=255, null=True, blank=True)

    def get_absolute_url(self):
        return reverse('fieldslip-detail', args=[str(self.id)])

    def __str__(self):
        return self.field_number


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

# AccessionReference Model
class AccessionReference(BaseModel):
    accession = models.ForeignKey(Accession, on_delete=models.CASCADE)
    reference = models.ForeignKey(Reference, on_delete=models.CASCADE)
    page = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        unique_together = ('accession', 'reference')

    def get_absolute_url(self):
        return reverse('accessionreference-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.accession} - {self.reference}"


# AccessionRow Model
class AccessionRow(BaseModel):
    accession = models.ForeignKey(Accession, on_delete=models.CASCADE)
    storage = models.ForeignKey(Storage, on_delete=models.CASCADE, blank=True, null=True)
    specimen_suffix = models.CharField(max_length=255, blank=True, null=True)

    def get_absolute_url(self):
        return reverse('accessionrow-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.accession} {self.specimen_suffix}" 
    class Meta:
        unique_together = ('accession', 'specimen_suffix')

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
    taxon = models.ForeignKey('Taxon', on_delete=models.SET_NULL, null=True, blank=True)
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

