from decimal import Decimal, InvalidOperation
import warnings

from crum import get_current_user
from django.db import models
from django.db.models.functions import TruncDate
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django_userforeignkey.models.fields import UserForeignKey
from django.db.models import Count, Sum, UniqueConstraint
from django.contrib.auth.models import User
from simple_history.models import HistoricalRecords
import os # For file handling in media class
from django.core.exceptions import ValidationError
import string # For generating specimen number
from typing import Any, Dict, Optional
import uuid
from django.utils.translation import gettext_lazy as _
User = get_user_model()


MANUAL_QC_SOURCE = "manual_qc"

from .merge import MergeMixin, MergeStrategy
from .notifications import notify_media_qc_transition


class InventoryStatus(models.TextChoices):
    """Status options for inventory sessions."""
    PRESENT = "present", "Present"
    MISSING = "missing", "Missing"
    UNKNOWN = "unknown", "Unknown"


class PlaceRelation(models.TextChoices):
    PART_OF = "partOf", "Part Of"
    SYNONYM = "synonym", "Synonym"
    ABBREVIATION = "abbreviation", "Abbreviation"


class PlaceType(models.TextChoices):
    REGION = "Region", "Region"
    SITE = "Site", "Site"
    COLLECTING_AREA = "CollectingArea", "Collecting Area"
    SQUARE = "square", "Square"



class BaseModel(models.Model):
    created_on = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date Created",
        help_text="Timestamp when this record was created.",
    )
    modified_on = models.DateTimeField(
        auto_now=True,
        verbose_name="Date Modified",
        help_text="Timestamp when this record was last updated.",
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
        verbose_name="Created by",
        help_text="User who created this record."
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_modified",
        verbose_name="Modified by",
        help_text="User who most recently updated this record."
    )

    class Meta:
        abstract = True
        ordering = ["-created_on"]
        verbose_name = "Base Record"
        verbose_name_plural = "Base Records"

    def clean(self):
        user = get_current_user()
        if not user or isinstance(user, AnonymousUser):
            raise ValidationError("You must be logged in to perform this action.")

    def save(self, *args, **kwargs):
        self.clean()  # ensure validation before saving
        user = get_current_user()
        if user and not isinstance(user, AnonymousUser):
            if not self.pk and not self.created_by:
                self.created_by = user
            self.modified_by = user
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        user = get_current_user()
        if not user or isinstance(user, AnonymousUser):
            raise ValidationError("You must be logged in to delete this record.")
        super().delete(*args, **kwargs)


def _resolve_user_organisation(user: User | None) -> Optional["Organisation"]:
    """Return the organisation for a user when a membership exists."""

    if user is None:
        return None

    membership = getattr(user, "organisation_membership", None)
    if membership is None:
        return None

    return membership.organisation


class AccessionNumberSeriesQuerySet(models.QuerySet):
    """Query helpers for organisation-aware accession number series lookups."""

    def for_user(self, user: User):
        organisation = _resolve_user_organisation(user)
        queryset = self.filter(user=user)
        if organisation is not None:
            queryset = queryset.filter(organisation=organisation)
        return queryset

    def active_for_user(self, user: User):
        return self.for_user(user).filter(is_active=True)


class AccessionNumberSeriesManager(models.Manager.from_queryset(AccessionNumberSeriesQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related("organisation", "user")


class Organisation(BaseModel):
    """Organisation grouping users and accession number series ownership."""

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text=_("Display name for the organisation."),
    )
    code = models.SlugField(
        max_length=50,
        unique=True,
        help_text=_("Short code used to identify the organisation."),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether the organisation can be assigned to users and series."),
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]
        verbose_name = _("Organisation")
        verbose_name_plural = _("Organisations")

    def clean(self):
        # Allow system-level creation where no request user is available (e.g. migrations).
        user = get_current_user()
        if not user or isinstance(user, AnonymousUser):
            return None
        return super().clean()

    def __str__(self):
        return self.name


class UserOrganisation(BaseModel):
    """One-to-one mapping connecting a user to an organisation."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="organisation_membership",
        help_text=_("User assigned to an organisation."),
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="memberships",
        help_text=_("Organisation the user belongs to."),
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("User organisation")
        verbose_name_plural = _("User organisations")

    def clean(self):
        user = get_current_user()
        if not user or isinstance(user, AnonymousUser):
            return None
        return super().clean()

    def __str__(self):
        return f"{self.user} → {self.organisation}"


class MergeLog(BaseModel):
    """Audit trail capturing the outcome of merge operations."""

    model_label = models.CharField(
        max_length=255,
        help_text="Dotted label of the model the merge acted upon.",
    )
    source_pk = models.CharField(
        max_length=255,
        help_text="Primary key of the source record that was merged.",
    )
    target_pk = models.CharField(
        max_length=255,
        help_text="Primary key of the target record that received the data.",
    )
    resolved_values = models.JSONField(
        help_text="Final values applied to the target record.",
    )
    relation_actions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Actions executed against related objects during the merge.",
    )
    strategy_map = models.JSONField(
        help_text="Strategies that were used to resolve field conflicts.",
    )
    source_snapshot = models.JSONField(
        null=True,
        blank=True,
        help_text="Serialised representation of the source record before merge.",
    )
    target_before = models.JSONField(
        help_text="Serialised state of the target record before the merge.",
    )
    target_after = models.JSONField(
        help_text="Serialised state of the target record after the merge.",
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merge_logs",
        help_text="User that triggered the merge, when available.",
    )
    executed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the merge completed.",
    )

    class Meta:
        ordering = ["-executed_at"]
        verbose_name = "Merge Log Entry"
        verbose_name_plural = "Merge Log Entries"

    def clean(self):
        # Override BaseModel.clean to allow system initiated writes without an
        # authenticated request user being available.
        return None

    def save(self, *args, **kwargs):
        if self.performed_by and not self.created_by:
            self.created_by = self.performed_by
        if self.performed_by and not self.modified_by:
            self.modified_by = self.performed_by
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Merge {self.source_pk} → {self.target_pk} ({self.model_label})"

# Locality Model
class Locality(BaseModel):
    class GeologicalTime(models.TextChoices):
        MIOCENE = "M", _("Miocene")
        PLIOCENE = "Pi", _("Pliocene")
        PLEISTOCENE = "Pe", _("Pleistocene")
        HOLOCENE = "H", _("Holocene")

    abbreviation = models.CharField(
        max_length=2,
        unique=True,
        help_text="Enter the Abbreviation of the Locality",
    )
    name = models.CharField(max_length=50, help_text="The name of the Locality.")
    geological_times = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Selected geological time abbreviations for this locality."),
        verbose_name=_("Geological time"),
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def get_absolute_url(self):
        return reverse("locality_detail", args=[str(self.id)])

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Locality"
        verbose_name_plural = "Localities"

    def clean(self):
        super().clean()
        times = self.geological_times or []
        if not isinstance(times, list):
            raise ValidationError(
                {"geological_times": _("Geological times must be a list of values.")}
            )

        invalid = [value for value in times if value not in self.GeologicalTime.values]
        if invalid:
            raise ValidationError(
                {
                    "geological_times": _(
                        "Invalid geological time selection: %(invalid)s"
                    )
                    % {"invalid": ", ".join(invalid)}
                }
            )

        # Ensure stored list does not contain duplicates while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for value in times:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        self.geological_times = deduped

    def get_geological_times_display(self) -> list[str]:
        display_labels: list[str] = []
        for value in self.geological_times:
            try:
                display_labels.append(self.GeologicalTime(value).label)
            except ValueError:
                display_labels.append(value)
        return display_labels

    def geological_times_label_display(self) -> str:
        return "/".join(str(label) for label in self.get_geological_times_display())

    geological_times_label_display.short_description = _("Geological time(s)")
    geological_times_label_display.admin_order_field = "geological_times"

    def geological_times_abbreviation_display(self) -> str:
        return "/".join(self.geological_times)


class Place(BaseModel):
    locality = models.ForeignKey(
        "Locality",
        on_delete=models.CASCADE,
        related_name="places",
        help_text="Locality that contains this place.",
    )
    related_place = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_places",
        help_text="Another place linked to this place (if applicable).",
    )
    relation_type = models.CharField(
        max_length=20,
        choices=PlaceRelation.choices,
        null=True,
        blank=True,
        help_text="Type of relationship with the related place.",
    )
    name = models.CharField(
        max_length=100,
        help_text="Name of the place.",
    )
    place_type = models.CharField(
        max_length=20,
        choices=PlaceType.choices,
        help_text="Type of place within the locality hierarchy.",
    )
    description = models.TextField(
        null=True,
        blank=True,
        help_text="Detailed description of the place.",
    )
    comment = models.TextField(
        null=True,
        blank=True,
        help_text="Additional notes about the place.",
    )
    part_of_hierarchy = models.CharField(
        max_length=255,
        editable=False,
        help_text="Auto-generated hierarchy string for this place.",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.related_place and not self.relation_type:
            raise ValidationError({"relation_type": "Relation type is required when related place is set."})
        if not self.related_place and self.relation_type:
            raise ValidationError({"related_place": "Related place is required when relation type is set."})
        if self.related_place:
            if self.locality_id != self.related_place.locality_id:
                raise ValidationError({"related_place": "Related place must belong to the same locality."})
            if self.relation_type == PlaceRelation.PART_OF:
                ancestor = self.related_place
                while ancestor:
                    if ancestor.pk == self.pk:
                        raise ValidationError({"related_place": "Cannot set a higher-level place as part of its descendant."})
                    if ancestor.relation_type == PlaceRelation.PART_OF:
                        ancestor = ancestor.related_place
                    else:
                        break

    def save(self, *args, **kwargs):
        if self.related_place:
            if self.relation_type == PlaceRelation.PART_OF:
                self.part_of_hierarchy = f"{self.related_place.part_of_hierarchy} | {self.name}"
            else:
                self.part_of_hierarchy = self.related_place.part_of_hierarchy
        else:
            self.part_of_hierarchy = self.name
        super().save(*args, **kwargs)

# Collection Model
class Collection(BaseModel):
    abbreviation = models.CharField(
        max_length=4,
        help_text="Short code used to identify the collection.",
    )
    description = models.CharField(
        max_length=250,
        help_text="Full description or name of the collection.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('collection-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"

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
    instance_number = models.PositiveIntegerField(
        default=1,
        help_text="Instance of the specimen number for handling known duplicates."
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
    is_published = models.BooleanField(
        default=False,
        help_text="Indicates whether this accession has been cited in references.",
    )
    history = HistoricalRecords()

    @property
    def manual_import_media(self):
        """Return the first related media item originating from a manual QC import."""

        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("media")
        if prefetched is not None:
            for media in prefetched:
                if getattr(media, "is_manual_import", False):
                    return media

        for media in self.media.all():
            if getattr(media, "is_manual_import", False):
                return media
        return None

    def get_manual_import_metadata(self) -> Optional[Dict[str, Any]]:
        media = self.manual_import_media
        if media is None:
            return None
        return media.get_manual_import_metadata()

    @property
    def is_manual_import(self) -> bool:
        return self.get_manual_import_metadata() is not None

    def save(self, *args, **kwargs):
        """
        Auto-updates `is_published` based on related references.
        If references exist, it sets to True. If none exist, it sets to False.
        """
        if self.pk:  # Only check related objects if this object has a primary key
            self.is_published = self.accessionreference_set.exists()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('accession_detail', args=[str(self.id)])

    def __str__(self):
        collection_abbr = self.collection.abbreviation if self.collection else "N/A"
        prefix_abbr = self.specimen_prefix.abbreviation if self.specimen_prefix else "N/A"
        base = f"{collection_abbr}-{prefix_abbr} {self.specimen_no}"
        return f"{base} (#{self.instance_number})" if self.instance_number > 1 else base

    class Meta:
        ordering = ["collection", "specimen_prefix", "specimen_no"]
        verbose_name = "Accession"
        verbose_name_plural = "Accessions"
        unique_together = ('specimen_no', 'specimen_prefix', 'instance_number')

class AccessionNumberSeries(BaseModel):
    objects = AccessionNumberSeriesManager()

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="accession_number_series",
        null=True,
        blank=True,
        help_text="Organisation associated with this accession number range.",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="accession_series",
        help_text="User who owns this accession number range.",
    )
    start_from = models.PositiveIntegerField(
        help_text="First accession number in the range.",
    )
    end_at = models.PositiveIntegerField(
        help_text="Last accession number in the range.",
    )
    current_number = models.PositiveIntegerField(
        help_text="Next accession number to allocate.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this series is currently available for allocation.",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["organisation", "user", "start_from"]

    def clean(self):
        if not hasattr(self, "user") or self.user is None:
            return  # Let the form validator complain that user is required

        if self.organisation is None:
            resolved_organisation = _resolve_user_organisation(self.user)
            if resolved_organisation:
                self.organisation = resolved_organisation
        if self.organisation is None:
            raise ValidationError(
                _("An organisation is required for an accession number series."),
            )

        if self.start_from is None or self.end_at is None:
            return

        if self.start_from > self.end_at:
            raise ValidationError(_("Start number cannot exceed end number."))
        
        conflicting_series = (
            AccessionNumberSeries.objects.exclude(pk=self.pk)
            .filter(
                organisation=self.organisation,
                start_from__lte=self.end_at,
                end_at__gte=self.start_from,
            )
        )

        if conflicting_series.exists():
            raise ValidationError(
                "This accession number range overlaps with another range in the same series pool."
            )

        allow_multiple_active = getattr(self, "_allow_multiple_active", False)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_next_batch(self, count):
        if self.current_number + count - 1 > self.end_at:
            raise ValidationError("Not enough numbers left in this series.")
        batch = list(range(self.current_number, self.current_number + count))
        self.current_number += count
        self.save()
        return batch

# Subject Model
class Subject(BaseModel):
    subject_name = models.CharField(
        max_length=50,
        help_text="Name of the comment subject.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('subject-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def __str__(self):
        return self.subject_name


# Comment Model
class Comment(BaseModel):
    specimen_no = models.ForeignKey(
        Accession,
        on_delete=models.CASCADE,
        related_name='comments',
        help_text="Accession this comment relates to.",
    )
    comment = models.TextField(
        help_text="Comment text provided by the user.",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        help_text="Subject category for this comment.",
    )

    RESPONSE_STATUS = (
        ('N', 'New'),
        ('P', 'Pending'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
        ('C', 'Closed'),
    )
    
    status = models.CharField(max_length=50, choices=RESPONSE_STATUS, help_text="Please select your response")
    response = models.TextField(
        null=True,
        blank=True,
        help_text="Response text to the comment.",
    )
    comment_by = models.CharField(
        max_length=50,
        help_text="Name of the person who left the comment.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('comment-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Comment"
        verbose_name_plural = "Comments"

    def __str__(self):
        return self.comment


# FieldSlip Model
class FieldSlip(MergeMixin, BaseModel):
    merge_fields = {
        "field_number": MergeStrategy.FIELD_SELECTION,
        "verbatim_taxon": MergeStrategy.FIELD_SELECTION,
        "verbatim_element": MergeStrategy.FIELD_SELECTION,
    }
    relation_strategies = {
        "accession_links": {
            "action": "reassign",
            "deduplicate": True,
        }
    }
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

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('fieldslip_detail', args=[str(self.id)])

    def __str__(self):
        return self.field_number if self.field_number else "Unnamed Field Slip"

    class Meta:
        ordering = ["field_number"]
        verbose_name = "Field Slip"
        verbose_name_plural = "Field Slips"
        permissions = [("can_merge", "Can merge field slip records")]

# Storage Model
class Storage(MergeMixin, BaseModel):
    merge_fields = {
        "area": MergeStrategy.FIELD_SELECTION,
    }
    area = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        help_text="Name or code of the storage location.",
    )
    parent_area = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Broader storage location that contains this area.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('storage_detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Storage"
        verbose_name_plural = "Storages"
        permissions = [("can_merge", "Can merge storage records")]

    def __str__(self):
        return self.area


# Reference Model
class Reference(MergeMixin, BaseModel):
    merge_fields = {
        "title": MergeStrategy.FIELD_SELECTION,
        "citation": MergeStrategy.FIELD_SELECTION,
    }
    title = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        help_text="Title of the published work.",
    )
    first_author = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        help_text="Name of the first author of the work.",
    )
    year = models.CharField(
        max_length=4,
        blank=False,
        null=False,
        help_text="Publication year (YYYY).",
    )
    journal = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Journal or source where the work was published.",
    )
    volume = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="Volume information for the publication.",
    )
    issue = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="Issue number for the publication.",
    )
    pages = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="Page range within the publication.",
    )
    doi = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Digital Object Identifier (if available).",
    )
    citation = models.TextField(
        blank=False,
        null=False,
        help_text="Formatted citation text.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('reference_detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Reference"
        verbose_name_plural = "References"
        permissions = [("can_merge", "Can merge reference records")]

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
    history = HistoricalRecords()

    class Meta:
        unique_together = ("accession", "fieldslip")  # Ensures no duplicate relations
        ordering = ["accession", "fieldslip"]
        verbose_name = "Accession-FieldSlip Link"
        verbose_name_plural = "Accession-FieldSlip Links"

    def __str__(self):
        return f"{self.accession} ↔ {self.fieldslip}"

# AccessionReference Model
class AccessionReference(BaseModel):
    accession = models.ForeignKey(
        Accession,
        on_delete=models.CASCADE,
        help_text="Accession linked to the reference.",
    )
    reference = models.ForeignKey(
        Reference,
        on_delete=models.CASCADE,
        help_text="Reference that cites the accession.",
    )
    page = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="Page or figure citation within the reference.",
    )
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['accession', 'reference'],
                name='unique_accession_reference'
            )
        ]

    def get_absolute_url(self):
        return reverse('accessionreference-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Accession Reference"
        verbose_name_plural = "Accession References"

    def __str__(self):
        return f"{self.accession} - {self.reference} (Page: {self.page or 'N/A'})"

# AccessionRow Model
class AccessionRow(BaseModel):
    accession = models.ForeignKey(
        Accession,
        on_delete=models.CASCADE,
        help_text="Accession to which this row belongs.",
    )
    storage = models.ForeignKey(
        Storage,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Storage location for this specimen instance.",
    )
    specimen_suffix = models.CharField(
        max_length=25,
        blank=True,
        null=True,
        default='-',
        help_text="Suffix distinguishing multiple items under the same accession.",
    )
    status = models.CharField(
        max_length=10,
        choices=InventoryStatus.choices,
        blank=True,
        null=True,
        help_text="Inventory status of the specimen",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('accessionrow_detail', args=[str(self.id)])

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
        verbose_name = "Accession Row"
        verbose_name_plural = "Accession Rows"

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
        """Assign the next available suffix only when none is provided."""
        if self.specimen_suffix in (None, ""):
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


class UnexpectedSpecimen(BaseModel):
    identifier = models.CharField(
        max_length=255,
        help_text="Identifier assigned to the unexpected specimen.",
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Unexpected Specimen"
        verbose_name_plural = "Unexpected Specimens"

    def __str__(self):
        return self.identifier

# NatureOfSpecimen Model
class NatureOfSpecimen(BaseModel):
    accession_row = models.ForeignKey(
        AccessionRow,
        on_delete=models.CASCADE,
        help_text="Accession row describing this specimen.",
    )
    element = models.ForeignKey(
        'Element',
        on_delete=models.CASCADE,
        help_text="Element represented by the specimen.",
    )
    side = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Side of the body or element, if applicable.",
    )
    condition = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Observed condition of the specimen.",
    )
    verbatim_element = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Element description as originally recorded.",
    )
    portion = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Portion of the element represented by the specimen.",
    )
    fragments = models.IntegerField(
        default=0,
        help_text="Number of fragments associated with this specimen.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('natureofspecimen-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Nature Of Specimen"
        verbose_name_plural = "Nature Of Specimens"

    def __str__(self):
        return f"NatureOfSpecimen for AccessionRow {self.accession_row}"


# Element Model
class Element(MergeMixin, BaseModel):
    """Hierarchical anatomical element tracked with audit history.

    Merge preparation notes:
    - Parent links cascade on delete, so merge flows should reparent children before
      removing any source records.
    - No uniqueness constraints on name or parent; duplicates may need FIELD_SELECTION
      and deduplication strategies during merge.
    """

    merge_fields = {
        "name": MergeStrategy.FIELD_SELECTION,
        "parent_element": MergeStrategy.FIELD_SELECTION,
    }

    relation_strategies = {
        "children": {"action": "reassign", "deduplicate": True},
        "natureofspecimen_set": {"action": "reassign", "deduplicate": True},
    }
    parent_element = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text="Broader anatomical element in the hierarchy.",
    )
    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        help_text="Name of the anatomical element.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('element-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Element"
        verbose_name_plural = "Elements"
        permissions = [("can_merge", "Can merge element records")]
        ordering = ['parent_element__name', 'name']

    def __str__(self):
        return self.name


# Person Model
class Person(BaseModel):
    first_name = models.CharField(
        max_length=255,
        help_text="Person's first name.",
    )
    last_name = models.CharField(
        max_length=255,
        help_text="Person's last name.",
    )
    orcid = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="ORCID identifier for the person, if available.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('person-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Persons"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


# Identification Model
class Identification(BaseModel):
    accession_row = models.ForeignKey(
        AccessionRow,
        on_delete=models.CASCADE,
        help_text="Specimen instance that was identified.",
    )
    identified_by = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Person who made the identification.",
    )
    taxon_verbatim = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_(
            "Lowest level of taxonomy provided for the identification; matched to the controlled taxonomy when possible."
        ),
    )
    taxon = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Determined taxon name.",
    )
    taxon_record = models.ForeignKey(
        "Taxon",
        on_delete=models.PROTECT,
        related_name="identifications",
        null=True,
        blank=True,
        help_text=_("Linked taxon from the controlled taxonomy."),
    )
    reference = models.ForeignKey(
        Reference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Reference supporting the identification, if any.",
    )
    date_identified = models.DateField(
        null=True,
        blank=True,
        help_text="Date when the identification was made.",
    )
    identification_qualifier = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Qualifier indicating certainty (cf., aff., etc.).",
    )
    verbatim_identification = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Identification text as originally recorded.",
    )
    identification_remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Additional remarks about the identification.",
    )
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('identification-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Identification"
        verbose_name_plural = "Identifications"

    def __str__(self):
        display_name = self.preferred_taxon_name or ""
        if display_name:
            return f"Identification for AccessionRow {self.accession_row} ({display_name})"
        return f"Identification for AccessionRow {self.accession_row}"

    def clean(self):
        super().clean()
        self._sync_taxon_fields()
        if not self.taxon_verbatim:
            raise ValidationError(
                {"taxon_verbatim": _("Provide the lowest taxon for this identification.")}
            )
        if self.taxon_record and self.taxon_record.status != TaxonStatus.ACCEPTED:
            raise ValidationError(
                {"taxon_record": _("Identifications must reference an accepted taxon.")}
            )

    def save(self, *args, **kwargs):
        self._sync_taxon_fields()
        super().save(*args, **kwargs)

    def _sync_taxon_fields(self) -> None:
        """Keep legacy and unified taxon fields consistent and auto-link controlled records."""

        original_taxon = self.taxon
        original_taxon_record_id = self.taxon_record_id
        original_verbatim = self.taxon_verbatim

        if self.taxon_verbatim:
            self.taxon_verbatim = self.taxon_verbatim.strip()

        if self.taxon_verbatim and self.taxon != self.taxon_verbatim:
            # Keep legacy column populated for backwards compatibility while it exists.
            self.taxon = self.taxon_verbatim

        matched_taxon = self._match_controlled_taxon(self.taxon_verbatim)
        self.taxon_record = matched_taxon

        if (
            original_taxon != self.taxon
            or original_taxon_record_id != self.taxon_record_id
            or original_verbatim != self.taxon_verbatim
        ):
            self._change_reason = _("Taxonomy synchronized with unified taxon fields.")

    @property
    def preferred_taxon_name(self) -> Optional[str]:
        """Return the controlled taxon name if available, otherwise verbatim text."""

        if self.taxon_record:
            return self.taxon_record.taxon_name
        return self.taxon or self.taxon_verbatim

    @property
    def has_controlled_taxon(self) -> bool:
        return bool(self.taxon_record_id)

    def deprecated_taxon_usage(self) -> str:
        warnings.warn(
            "Identification.taxon is deprecated; use taxon_verbatim for free-text values.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.taxon_verbatim or self.taxon or ""

    def _match_controlled_taxon(self, taxon_name: Optional[str]) -> Optional["Taxon"]:
        """Return a unique accepted, active Taxon that matches the provided name."""

        if not taxon_name:
            return None

        matches = list(
            Taxon.objects.filter(
                taxon_name__iexact=taxon_name,
                status=TaxonStatus.ACCEPTED,
                is_active=True,
            )[:2]
        )

        if len(matches) == 1:
            return matches[0]

        return None


# Taxon Model

class TaxonExternalSource(models.TextChoices):
    NOW = "NOW", _("NOW")
    PBDB = "PBDB", _("PBDB")
    LEGACY = "LEGACY", _("Legacy")


class TaxonStatus(models.TextChoices):
    ACCEPTED = "accepted", _("Accepted")
    SYNONYM = "synonym", _("Synonym")
    INVALID = "invalid", _("Invalid")


class TaxonRank(models.TextChoices):
    KINGDOM = "kingdom", _("Kingdom")
    PHYLUM = "phylum", _("Phylum")
    CLASS = "class", _("Class")
    ORDER = "order", _("Order")
    SUPERFAMILY = "superfamily", _("Superfamily")
    FAMILY = "family", _("Family")
    SUBFAMILY = "subfamily", _("Subfamily")
    TRIBE = "tribe", _("Tribe")
    GENUS = "genus", _("Genus")
    SPECIES = "species", _("Species")
    SUBSPECIES = "subspecies", _("Subspecies")


TAXON_RANK_CHOICES = TaxonRank.choices

class Taxon(BaseModel):
    external_source = models.CharField(
        max_length=16,
        choices=TaxonExternalSource.choices,
        default=TaxonExternalSource.LEGACY,
        help_text=_("External source that provided this taxon."),
    )
    external_id = models.CharField(
        max_length=191,
        blank=True,
        null=True,
        help_text=_("Stable identifier supplied by the external source."),
    )
    author_year = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Authorship information associated with the name."),
    )
    status = models.CharField(
        max_length=16,
        choices=TaxonStatus.choices,
        default=TaxonStatus.ACCEPTED,
        help_text=_("Curation status for the taxon record."),
    )
    accepted_taxon = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="synonyms",
        limit_choices_to={"status": TaxonStatus.ACCEPTED},
        help_text=_("Accepted taxon referenced when this record is a synonym."),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text=_("Immediate parent in the taxonomic hierarchy, when available."),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Indicates whether the taxon should be treated as active."),
    )
    source_version = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Version or commit identifier for the external source."),
    )
    taxon_rank = models.CharField(
        max_length=50,
        choices=TAXON_RANK_CHOICES,
        help_text="Taxonomic rank represented by this record.",
    )
    taxon_name = models.CharField(
        max_length=50,
        help_text="Primary taxon name for the selected rank.",
    )
    kingdom = models.CharField(
        max_length=255,
        help_text="Kingdom assignment for the taxon.",
    )
    phylum = models.CharField(
        max_length=255,
        help_text="Phylum assignment for the taxon.",
    )
    class_name = models.CharField(
        max_length=255,
        help_text="Class assignment for the taxon.",
    )
    order = models.CharField(
        max_length=255,
        help_text="Order assignment for the taxon.",
    )
    superfamily = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default="",
        help_text="Superfamily assignment, if applicable.",
    )
    family = models.CharField(
        max_length=255,
        help_text="Family assignment for the taxon.",
    )
    subfamily = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default="",
        help_text="Subfamily assignment, if applicable.",
    )
    tribe = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default="",
        help_text="Tribal assignment, if applicable.",
    )
    genus = models.CharField(
        max_length=255,
        help_text="Genus portion of the taxon name.",
    )
    species = models.CharField(
        max_length=255,
        help_text="Species epithet of the taxon.",
    )
    infraspecific_epithet = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Infraspecific epithet (subspecies, variety, etc.).",
    )
    scientific_name_authorship = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Authorship citation for the scientific name.",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["class_name", "order", "family", "genus", "species"]
        verbose_name = "Taxon"
        verbose_name_plural = "Taxa"
        constraints = [
            models.UniqueConstraint(
                fields=["taxon_rank", "taxon_name", "scientific_name_authorship"],
                name="unique_taxon_rank_name_authorship",
            ),
            models.UniqueConstraint(
                fields=["external_source", "external_id"],
                name="unique_taxon_external_source_id",
                condition=(
                    models.Q(external_source__isnull=False, external_id__isnull=False)
                    & ~models.Q(external_id="")
                ),
            ),
            models.CheckConstraint(
                check=(
                    models.Q(status=TaxonStatus.ACCEPTED, accepted_taxon__isnull=True)
                    | models.Q(status=TaxonStatus.SYNONYM, accepted_taxon__isnull=False)
                    | models.Q(status=TaxonStatus.INVALID)
                ),
                name="taxon_status_consistency",
            ),
        ]
        indexes = [
            models.Index(fields=["external_source", "external_id"], name="taxon_external_idx"),
            models.Index(fields=["status"], name="taxon_status_idx"),
            models.Index(fields=["taxon_rank"], name="taxon_rank_idx"),
            models.Index(fields=["is_active"], name="taxon_active_idx"),
        ]
        permissions = [
            ("can_sync", "Can sync external taxonomy data"),
        ]

    def clean(self):
        super().clean()
        if not self.family and (self.genus or self.species):
            raise ValidationError("Genus and species must have a family.")
        if not self.genus and self.species:
            raise ValidationError("Species must have a genus.")
        if self.status == TaxonStatus.ACCEPTED and self.accepted_taxon_id:
            raise ValidationError({"accepted_taxon": _("Accepted taxa cannot reference another accepted taxon.")})
        if self.status == TaxonStatus.SYNONYM:
            if not self.accepted_taxon_id:
                raise ValidationError({"accepted_taxon": _("Synonym records must reference an accepted taxon.")})
            if self.accepted_taxon_id == self.pk:
                raise ValidationError({"accepted_taxon": _("A taxon cannot be a synonym of itself.")})
            if self.accepted_taxon and self.accepted_taxon.status != TaxonStatus.ACCEPTED:
                raise ValidationError({"accepted_taxon": _("Synonyms must reference an accepted taxon.")})
        if self.status != TaxonStatus.SYNONYM and self.accepted_taxon_id:
            raise ValidationError({"accepted_taxon": _("Only synonym records may reference an accepted taxon.")})
        if self.parent_id is not None and self.parent_id == self.pk:
            raise ValidationError({"parent": _("A taxon cannot be its own parent.")})

    def get_absolute_url(self):
        return reverse('taxon-detail', args=[str(self.id)])

    def __str__(self):
        if self.genus and self.species:
            if self.infraspecific_epithet:
                return f"{self.genus} {self.species} {self.infraspecific_epithet}"
            return f"{self.genus} {self.species}"
        return self.taxon_name

    @property
    def is_synonym(self) -> bool:
        return self.status == TaxonStatus.SYNONYM

    @property
    def is_accepted(self) -> bool:
        return self.status == TaxonStatus.ACCEPTED


class TaxonomyImport(BaseModel):
    class Source(models.TextChoices):
        NOW = "NOW", _("NOW")

    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.NOW,
        help_text=_("External taxonomy source for this import."),
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Timestamp when the import process started."),
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp when the import process finished."),
    )
    source_version = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Identifier or commit hash describing the imported data."),
    )
    counts = models.JSONField(
        default=dict,
        help_text=_("Summary counts for created, updated, deactivated, and related metrics."),
    )
    report_json = models.JSONField(
        default=dict,
        help_text=_("Detailed diff or issue information captured during the import."),
    )
    ok = models.BooleanField(
        default=False,
        help_text=_("Indicates whether the import completed successfully."),
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("Taxonomy Import")
        verbose_name_plural = _("Taxonomy Imports")

    def __str__(self) -> str:
        label = self.get_source_display()
        if self.source_version:
            return f"{label} import {self.source_version}"
        return f"{label} import"

    def mark_finished(
        self,
        *,
        ok: Optional[bool] = None,
        counts: Optional[Dict[str, Any]] = None,
        report: Optional[Dict[str, Any]] = None,
    ) -> None:
        if ok is not None:
            self.ok = ok
        if counts is not None:
            self.counts = counts
        if report is not None:
            self.report_json = report
        self.finished_at = timezone.now()
        self.save(update_fields=["ok", "counts", "report_json", "finished_at", "modified_on", "modified_by"])


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
    
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Stable public identifier for the media entry.",
    )
    accession = models.ForeignKey('Accession', null=True, blank=True, on_delete=models.CASCADE, related_name='media', help_text="Accession this media belongs to")
    accession_row = models.ForeignKey('AccessionRow', null=True, blank=True, on_delete=models.CASCADE, related_name='media', help_text="Accession row this media belongs to")
    scanning = models.ForeignKey(
        'Scanning',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='media',
        help_text="Scanning session associated with this media",
    )
    file_name = models.CharField(max_length=255, null=True, blank=True, help_text="The name of the media file")
    type = models.CharField(max_length=50, null=True, blank=True, choices=MEDIA_TYPE_CHOICES, help_text="Type of the media (e.g., photo, video, etc.)")
    format = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=MEDIA_FORMAT_CHOICES,
        help_text="File format of the media (supported formats: 'jpg', 'jpeg', 'png', 'gif', 'bmp')"
    )
    media_location = models.ImageField(
        upload_to="uploads/",
        help_text="Uploaded media file.",
    )
    license = models.CharField(max_length=30, choices=LICENSE_CHOICES
                               ,default='CC0'  # Default to public domain
                               , help_text="License information for the media file")
    rights_holder = models.CharField(max_length=255, null=True, blank=True, help_text="The individual or organization holding rights to the media")
    class OCRStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class QCStatus(models.TextChoices):
        PENDING_INTERN = "pending_intern", "Pending Intern Review"
        PENDING_EXPERT = "pending_expert", "Pending Expert Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    ocr_data = models.JSONField(null=True, blank=True, help_text="OCR extracted data")
    ocr_status = models.CharField(max_length=20, choices=OCRStatus.choices, default=OCRStatus.PENDING, help_text="Status of OCR processing")
    qc_status = models.CharField(
        max_length=20,
        choices=QCStatus.choices,
        default=QCStatus.PENDING_INTERN,
        help_text="Current quality control status for this media entry.",
    )
    intern_checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="media_qc_intern_checked",
        null=True,
        blank=True,
        help_text="Intern reviewer who most recently advanced this media for expert review.",
    )
    intern_checked_on = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the intern review was completed.",
    )
    expert_checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="media_qc_expert_checked",
        null=True,
        blank=True,
        help_text="Expert reviewer who most recently completed QC on this media.",
    )
    expert_checked_on = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the expert review was completed.",
    )
    rows_rearranged = models.BooleanField(
        default=False,
        help_text="Indicates if specimen rows were rearranged to match the media content during QC.",
    )
    history = HistoricalRecords()

    MANUAL_IMPORT_SOURCE = MANUAL_QC_SOURCE

    def get_manual_import_metadata(self) -> Optional[Dict[str, Any]]:
        """Return manual import metadata embedded in the OCR payload, if any."""

        data = self.ocr_data if isinstance(self.ocr_data, dict) else None
        if not data:
            return None
        metadata = data.get("_manual_import")
        if not isinstance(metadata, dict):
            return None
        source = metadata.get("source")
        if source and source != self.MANUAL_IMPORT_SOURCE:
            return None
        return metadata

    @property
    def is_manual_import(self) -> bool:
        return self.get_manual_import_metadata() is not None

    def manual_import_display(self) -> Optional[str]:
        metadata = self.get_manual_import_metadata()
        if not metadata:
            return None
        row_id = metadata.get("row_id")
        created_by = metadata.get("created_by")
        if row_id and created_by:
            return f"{row_id} — {created_by}"
        return row_id or created_by

    def save(self, *args, **kwargs):
        user_override_set = hasattr(self, "_force_qc_user")
        if user_override_set:
            user = getattr(self, "_force_qc_user")
        else:
            user = get_current_user()
        if isinstance(user, AnonymousUser):
            user = None

        previous = None
        if self.pk:
            previous = self.__class__.objects.filter(pk=self.pk).first()

        if self.media_location:
            self.file_name = os.path.basename(self.media_location.name)
            self.format = os.path.splitext(self.media_location.name)[1].lower().strip('.')

        status_changed = previous and previous.qc_status != self.qc_status
        ocr_changed = previous and previous.ocr_data != self.ocr_data
        rows_rearranged_changed = previous and previous.rows_rearranged != self.rows_rearranged

        note = getattr(self, "_qc_transition_note", None)

        if status_changed:
            timestamp = timezone.now()
            if self.qc_status in {
                self.QCStatus.PENDING_EXPERT,
                self.QCStatus.APPROVED,
                self.QCStatus.REJECTED,
            }:
                if not self.intern_checked_on:
                    self.intern_checked_on = timestamp
                if user and not getattr(self, "intern_checked_by_id", None):
                    self.intern_checked_by = user
            if self.qc_status in {self.QCStatus.APPROVED, self.QCStatus.REJECTED}:
                if not self.expert_checked_on:
                    self.expert_checked_on = timestamp
                if user and not getattr(self, "expert_checked_by_id", None):
                    self.expert_checked_by = user

        super().save(*args, **kwargs)

        if status_changed:
            description = (
                f"Status changed from {previous.get_qc_status_display()} to {self.get_qc_status_display()}"
                if previous
                else f"Status set to {self.get_qc_status_display()}"
            )
            if note:
                description = f"{description} — {note}" if description else note
            MediaQCLog.objects.create(
                media=self,
                change_type=MediaQCLog.ChangeType.STATUS,
                field_name="qc_status",
                old_value={"qc_status": previous.qc_status} if previous else None,
                new_value={"qc_status": self.qc_status},
                description=description,
                changed_by=user,
            )

        if ocr_changed:
            MediaQCLog.objects.create(
                media=self,
                change_type=MediaQCLog.ChangeType.OCR_DATA,
                field_name="ocr_data",
                old_value=previous.ocr_data if previous else None,
                new_value=self.ocr_data,
                description="OCR data updated during QC.",
                changed_by=user,
            )

        if rows_rearranged_changed:
            MediaQCLog.objects.create(
                media=self,
                change_type=MediaQCLog.ChangeType.ROWS_REARRANGED,
                field_name="rows_rearranged",
                old_value={"rows_rearranged": previous.rows_rearranged},
                new_value={"rows_rearranged": self.rows_rearranged},
                description="Rows rearranged flag updated.",
                changed_by=user,
            )

        if user_override_set and hasattr(self, "_force_qc_user"):
            delattr(self, "_force_qc_user")
        if hasattr(self, "_qc_transition_note"):
            delattr(self, "_qc_transition_note")

    def clean(self):
        super().clean()
        if self.media_location:
            valid_formats = ['jpg', 'jpeg', 'png', 'gif', 'bmp']
            extension = os.path.splitext(self.media_location.name)[1].lower().strip('.')
            if extension not in valid_formats:
                raise ValidationError(f"Invalid file format: {extension}. Supported formats are: {', '.join(valid_formats)}.")

    def get_absolute_url(self):
        return reverse('media-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Media"
        verbose_name_plural = "Medias"

    def __str__(self):
        return f"{self.file_name} ({self.type})"

    QC_ALLOWED_TRANSITIONS = {
        QCStatus.PENDING_INTERN: {
            QCStatus.PENDING_EXPERT,
            QCStatus.APPROVED,
            QCStatus.REJECTED,
        },
        QCStatus.PENDING_EXPERT: {
            QCStatus.PENDING_INTERN,
            QCStatus.APPROVED,
            QCStatus.REJECTED,
        },
        QCStatus.APPROVED: {QCStatus.PENDING_INTERN, QCStatus.PENDING_EXPERT},
        QCStatus.REJECTED: {QCStatus.PENDING_INTERN, QCStatus.PENDING_EXPERT},
    }

    def transition_qc(
        self,
        new_status: str,
        user=None,
        note: str | None = None,
        resolution: dict[str, dict[str, object]] | None = None,
    ) -> dict:
        """Transition the media to a new QC status.

        The transition validates that the change is allowed, stamps reviewer
        metadata, records a :class:`MediaQCLog` entry, and, when moving to
        ``approved``, attempts to create accessions from the OCR payload. If
        accession creation detects conflicts, the transition is aborted and a
        ``ValidationError`` is raised so the QC UI can display the issue. When
        ``resolution`` is provided, it is forwarded to the importer so duplicate
        accession numbers can be resolved.
        """

        if new_status not in self.QCStatus.values:
            raise ValidationError({"qc_status": "Unrecognised QC status."})

        old_status = self.qc_status
        if new_status != old_status:
            allowed = self.QC_ALLOWED_TRANSITIONS.get(old_status, set())
            if new_status not in allowed:
                raise ValidationError(
                    {
                        "qc_status": (
                            f"Cannot transition from {self.get_qc_status_display()} "
                            f"to {self.QCStatus(new_status).label}."
                        )
                    }
                )

        if user is None:
            user = get_current_user()
        if isinstance(user, AnonymousUser):
            user = None

        created: list[dict] = []
        conflicts: list[dict] = []

        if new_status == self.QCStatus.APPROVED:
            from .ocr_processing import create_accessions_from_media

            result = create_accessions_from_media(self, resolution)
            created = result.get("created", [])
            conflicts = result.get("conflicts", [])
            if conflicts:
                summary_parts = []
                for conflict in conflicts:
                    key = conflict.get("key")
                    reason = (
                        conflict.get("message")
                        or conflict.get("reason")
                        or "Conflict detected"
                    )
                    if key:
                        summary_parts.append(f"{key}: {reason}")
                    else:
                        summary_parts.append(reason)
                summary = "; ".join(summary_parts)
                if note:
                    summary = f"{summary} — {note}"
                MediaQCLog.objects.create(
                    media=self,
                    change_type=MediaQCLog.ChangeType.STATUS,
                    field_name="qc_status",
                    old_value={"qc_status": old_status},
                    new_value={"qc_status": old_status},
                    description=f"Approval blocked: {summary}",
                    changed_by=user,
                )
                exc = ValidationError({"qc_status": summary})
                setattr(exc, "conflicts", conflicts)
                raise exc

        if new_status == old_status:
            if note:
                MediaQCLog.objects.create(
                    media=self,
                    change_type=MediaQCLog.ChangeType.STATUS,
                    field_name="qc_status",
                    old_value={"qc_status": old_status},
                    new_value={"qc_status": new_status},
                    description=note,
                    changed_by=user,
                )
            return {"created": created, "conflicts": conflicts}

        self.qc_status = new_status
        self._force_qc_user = user
        if note:
            self._qc_transition_note = note
        self.save()
        notify_media_qc_transition(
            self,
            old_status,
            new_status,
            user=user,
            note=note,
        )
        return {"created": created, "conflicts": conflicts}


class MediaQCLog(models.Model):
    class ChangeType(models.TextChoices):
        STATUS = "status", "QC Status"
        OCR_DATA = "ocr_data", "OCR Data"
        ROWS_REARRANGED = "rows_rearranged", "Rows Rearranged"

    media = models.ForeignKey('Media', on_delete=models.CASCADE, related_name='qc_logs')
    change_type = models.CharField(max_length=32, choices=ChangeType.choices)
    field_name = models.CharField(max_length=100, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    description = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='media_qc_logs',
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_on"]
        verbose_name = "Media QC Log"
        verbose_name_plural = "Media QC Logs"

    def __str__(self):
        return f"QC change on {self.media} at {self.created_on:%Y-%m-%d %H:%M:%S}"


class MediaQCComment(models.Model):
    log = models.ForeignKey(MediaQCLog, on_delete=models.CASCADE, related_name='comments')
    comment = models.TextField()
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='media_qc_comments',
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_on"]
        verbose_name = "Media QC Comment"
        verbose_name_plural = "Media QC Comments"

    def __str__(self):
        creator = self.created_by if self.created_by else "System"
        return f"Comment by {creator} on {self.log}"


class LLMUsageRecordQuerySet(models.QuerySet):
    def for_media(self, media: "Media | int") -> "LLMUsageRecordQuerySet":
        media_id = getattr(media, "pk", media)
        return self.filter(media_id=media_id)

    def totals_by_day(self):
        return (
            self.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
                total_tokens=Sum("total_tokens"),
                cost_usd=Sum("cost_usd"),
                record_count=Count("id"),
            )
            .order_by("day")
        )


class LLMUsageRecordManager(models.Manager.from_queryset(LLMUsageRecordQuerySet)):  # type: ignore[misc]
    pass


class LLMUsageRecord(models.Model):
    media = models.OneToOneField(
        "Media",
        on_delete=models.CASCADE,
        related_name="llm_usage_record",
    )
    model_name = models.CharField(max_length=255)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("0"))
    remaining_quota_usd = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latest remaining ChatGPT quota reported with this usage record.",
    )
    processing_seconds = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Measured time spent processing the OCR request in seconds.",
    )
    response_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: LLMUsageRecordManager = LLMUsageRecordManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Usage for {self.media_id}: {self.model_name}"

    @staticmethod
    def _coerce_int(value: object) -> int:
        if value in (None, ""):
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _coerce_decimal(value: object) -> Decimal:
        if value in (None, ""):
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    @classmethod
    def defaults_from_payload(cls, payload: dict[str, object]) -> dict[str, object]:
        prompt_tokens = cls._coerce_int(payload.get("prompt_tokens"))
        completion_tokens = cls._coerce_int(payload.get("completion_tokens"))
        total_tokens = cls._coerce_int(payload.get("total_tokens"))
        if total_tokens == 0 and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens

        prompt_cost = cls._coerce_decimal(payload.get("prompt_cost_usd"))
        completion_cost = cls._coerce_decimal(payload.get("completion_cost_usd"))
        total_cost = payload.get("total_cost_usd")
        if total_cost not in (None, ""):
            cost_usd = cls._coerce_decimal(total_cost)
        else:
            cost_usd = prompt_cost + completion_cost

        model_name = payload.get("model") or payload.get("model_name") or "unknown"
        response_id = payload.get("request_id") or payload.get("response_id")

        data: dict[str, object | None] = {
            "model_name": str(model_name),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "response_id": str(response_id) if response_id not in (None, "") else None,
        }

        remaining_quota = payload.get("remaining_quota") or payload.get("remaining_quota_usd")
        if remaining_quota not in (None, ""):
            data["remaining_quota_usd"] = cls._coerce_decimal(remaining_quota)

        duration = payload.get("processing_seconds") or payload.get("duration_seconds")
        if duration not in (None, ""):
            try:
                data["processing_seconds"] = Decimal(str(duration))
            except (InvalidOperation, TypeError, ValueError):
                pass

        return data

    def update_from_payload(self, payload: dict[str, object]) -> None:
        defaults = self.defaults_from_payload(payload)
        for field, value in defaults.items():
            setattr(self, field, value)
        self.save(update_fields=list(defaults.keys()) + ["updated_at"])


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
    history = HistoricalRecords()

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
    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('geologicalcontext-detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Geological Context"
        verbose_name_plural = "Geological Contexties"

    def __str__(self):
        return f"{self.name} ({self.unit_name})"
    
class PreparationMaterial(BaseModel):
    """ Materials used in the preparation process. """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the preparation material (e.g., Paraloid B72, Cyanoacrylate).")
    description = models.TextField(blank=True, null=True, help_text="Details about the material (e.g., properties, best use cases).")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Preparation Material"
        verbose_name_plural = "Preparation Materials"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('preparationmaterial-detail', args=[str(self.id)])


class PreparationStatus(models.TextChoices):
    """ Enum for tracking the preparation workflow stages. """
    PENDING = "Pending", "Pending"
    IN_PROGRESS = "In Progress", "In Progress"
    COMPLETED = "Completed", "Completed"
    APPROVED = "Approved", "Approved"
    DECLINED = "Declined", "Declined"


class Preparation(BaseModel):
    """ Tracks preparation and maintenance of specimens with curation approval. """
    
    accession_row = models.ForeignKey(
        AccessionRow, 
        on_delete=models.CASCADE, 
        related_name="preparations",
        help_text="The specimen undergoing preparation."
    )
    preparator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="preparations",
        help_text="The museum staff responsible for the preparation."
    )

    preparation_type = models.CharField(
        max_length=50, 
        choices=[
            ('cleaning', 'Cleaning'),
            ('consolidation', 'Consolidation'),
            ('casting', 'Casting'),
            ('repair', 'Repair'),
            ('restoration', 'Restoration'),
            ('conservation', 'Conservation'),
            ('mounting', 'Mounting'),
            ('other', 'Other')
        ], 
        help_text="The type of preparation or maintenance performed."
    )

    reason = models.TextField(
        null=True, 
        blank=True, 
        help_text="The reason for the preparation (e.g., exhibition, conservation, research)."
    )

    started_on = models.DateField(
        help_text="Date when preparation started."
    )
    completed_on = models.DateField(
        null=True, 
        blank=True, 
        help_text="Date when preparation was completed."
    )

    status = models.CharField(
        max_length=20,
        choices=PreparationStatus.choices,
        default=PreparationStatus.PENDING,
        help_text="Current status of the preparation process."
    )

    original_storage = models.ForeignKey(
        Storage, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="original_preparations",
        help_text="Where the specimen was stored before preparation."
    )
    temporary_storage = models.ForeignKey(
        Storage, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="temporary_preparations",
        help_text="Where the specimen was moved during preparation."
    )

    condition_before = models.TextField(
        null=True, 
        blank=True, 
        help_text="Condition of the specimen before preparation."
    )

    condition_after = models.TextField(
        null=True, 
        blank=True, 
        help_text="Condition of the specimen after preparation."
    )

    preparation_method = models.TextField(
        null=True, 
        blank=True, 
        help_text="Describe the preparation technique used (e.g., mechanical cleaning, acid preparation)."
    )

    chemicals_used = models.TextField(
        null=True, 
        blank=True, 
        help_text="List any chemicals or adhesives applied during the preparation."
    )

    materials_used = models.ManyToManyField(
        PreparationMaterial, 
        blank=True, 
        related_name="preparations",
        help_text="List of materials used in the preparation process."
    )

    media = models.ManyToManyField(
        Media,
        through="PreparationMedia",
        related_name="preparations",
        blank=True,
        help_text="Attach categorized media (before/after/in-progress)."
    )

    # === Curation Process ===
    curator = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="curated_preparations",
        help_text="The curator who reviews and approves/declines the preparation."
    )

    approval_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('declined', 'Declined')
        ],
        default='pending',
        help_text="Approval decision by the curator."
    )

    approval_date = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Timestamp when the curator made a decision."
    )

    curator_comments = models.TextField(
        null=True, 
        blank=True, 
        help_text="Curator's comments on the preparation (approval or rejection reasons)."
    )

    report_link = models.URLField(
        null=True,
        blank=True,
        help_text="Link to an external report or documentation for this preparation."
    )

    notes = models.TextField(
        null=True,
        blank=True,
        help_text="Additional notes or observations about the preparation."
    )
    history = HistoricalRecords()

    def clean(self):
        """
        Validation to ensure curator is different from the preparator,
        unless the curator is a superuser.
        """
        user = get_current_user()
        if self.curator and self.preparator:
            if self.curator == self.preparator and (not user or not user.is_superuser):
                raise ValidationError("The curator must be different from the preparator.")

    def save(self, *args, **kwargs):
        """ 
        Custom save method to enforce validation and track curation decisions. 
        """
        self.clean()  # Ensure validations are checked

        # Automatically set approval date if a curator approves or declines
        if self.approval_status in ["approved", "declined"] and not self.approval_date:
            self.approval_date = timezone.now()

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('preparation_detail', args=[str(self.id)])

    class Meta:
        verbose_name = "Preparation"
        verbose_name_plural = "Preparations"
        
    def __str__(self):
        return f"{self.accession_row} - {self.preparation_type} by {self.preparator}"


class PreparationMedia(BaseModel):
    preparation = models.ForeignKey(
        "Preparation",
        on_delete=models.CASCADE,
        help_text="Preparation record associated with this media.",
    )
    media = models.ForeignKey(
        "Media",
        on_delete=models.CASCADE,
        help_text="Media file linked to the preparation.",
    )

    MEDIA_CONTEXT_CHOICES = [
        ("before", "Before Preparation"),
        ("after", "After Preparation"),
        ("in_progress", "In Progress"),
        ("other", "Other")
    ]
    context = models.CharField(
        max_length=20,
        choices=MEDIA_CONTEXT_CHOICES,
        default="other",
        help_text="Indicates when this media was captured."
    )

    notes = models.TextField(null=True, blank=True, help_text="Optional comments or observations about this media.")
    history = HistoricalRecords()

    class Meta:
        unique_together = ("preparation", "media")
        verbose_name = "Preparation Media"
        verbose_name_plural = "Preparation Media"

    def __str__(self):
        return f"{self.preparation} - {self.get_context_display()}"


class DrawerRegister(BaseModel):
    code = models.CharField(max_length=3, unique=True, help_text="Three letter unique code")
    description = models.TextField(help_text="Description of the drawer or folder")
    localities = models.ManyToManyField(
        "Locality", blank=True, help_text="Related localities"
    )
    taxa = models.ManyToManyField(
        "Taxon", blank=True, help_text="Related taxa"
    )
    estimated_documents = models.PositiveIntegerField(
        help_text="Estimated number of documents or cards"
    )
    priority = models.PositiveIntegerField(
        default=0,
        help_text="Display order priority",
    )

    class ScanningStatus(models.TextChoices):
        WAITING = "waiting", "Waiting"
        IN_PROGRESS = "in_progress", "In progress"
        SCANNED = "scanned", "Scanned"

    scanning_status = models.CharField(
        max_length=20,
        choices=ScanningStatus.choices,
        default=ScanningStatus.WAITING,
        help_text="Current scanning workflow status.",
    )
    scanning_users = models.ManyToManyField(
        User,
        blank=True,
        related_name="drawerregisters",
        help_text="Users assigned to scanning",
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Drawer Register"
        verbose_name_plural = "Drawer Register"
        # Display entries with higher priority first; items without an
        # explicit priority (default ``0``) appear last.
        ordering = ["-priority", "code"]

    def clean(self):
        super().clean()

    def __str__(self):
        return f"{self.code}"

class Scanning(BaseModel):
    drawer = models.ForeignKey(
        DrawerRegister,
        on_delete=models.CASCADE,
        related_name="scans",
        help_text="Drawer register being scanned.",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="scans",
        help_text="User performing the scanning session.",
    )
    start_time = models.DateTimeField(
        help_text="Date and time the scanning session began.",
    )
    end_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date and time the scanning session ended.",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["-start_time"]

    def __str__(self):
        return f"{self.drawer.code} - {self.user} ({self.start_time})"
