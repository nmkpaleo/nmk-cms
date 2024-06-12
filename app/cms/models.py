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


class Locality(BaseModel):
    abbreviation = models.CharField(
        max_length=2, help_text="Enter the Abbreviation of the Locality"
    )
    name = models.CharField(max_length=50, help_text="The name of the Locality.")

    class Meta:
        ordering = ["name"]

    def get_absolute_url(self):
        return reverse("locality-detail", args=[str(self.id)])

    def __str__(self):
        return self.name


class Collection(BaseModel):
    abbreviation = models.CharField(max_length=4)
    description = models.CharField(max_length=250)

    def get_absolute_url(self):
        return reverse('collection-detail', args=[str(self.id)])

    def __str__(self):
        return self.description


class Accession(BaseModel):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    specimen_prefix = models.ForeignKey(Locality, on_delete=models.CASCADE)
    specimen_no = models.PositiveIntegerField()
    accessioned_by = models.ForeignKey(User, on_delete=models.CASCADE)
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

    type_status = models.CharField(max_length=50, choices=options)
    comment = models.TextField(null=True, blank=True)

    def get_absolute_url(self):
        return reverse('accession-detail', args=[str(self.id)])

    def __str__(self):
        return f"{self.specimen_prefix}{self.specimen_no}"


class Subject(BaseModel):
    subject_name = models.CharField(max_length=50)

    def get_absolute_url(self):
        return reverse('subject-detail', args=[str(self.id)])

    def __str__(self):
        return self.subject_name


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
    aerial_photo = models.CharField(max_length=255, null=True, blank=True)
    verbatim_latitude = models.CharField(max_length=255, null=True, blank=True)
    verbatim_longitude = models.CharField(max_length=255, null=True, blank=True)
    verbatim_SRS = models.CharField(max_length=255, null=True, blank=True)
    verbatim_coordinate_system = models.CharField(max_length=255, null=True, blank=True)
    verbatim_elevation = models.CharField(max_length=255, null=True, blank=True)
    accession = models.ForeignKey(Accession, on_delete=models.CASCADE, null=True, blank=True)

    def get_absolute_url(self):
        return reverse('fieldslip-detail', args=[str(self.id)])

    def __str__(self):
        return self.field_number

class Storage(BaseModel):
    area = models.CharField(max_length=255, blank=False, null=False)
    parent_area = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)

    def get_absolute_url(self):
        return reverse('storage-detail', args=[str(self.id)])

    def __str__(self):
        return self.area
