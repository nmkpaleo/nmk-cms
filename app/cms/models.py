from django.db import models
from django.urls import reverse
from django_userforeignkey.models.fields import UserForeignKey


# https://medium.com/@KevinPavlish/add-common-fields-to-all-your-django-models-bce033ac2cdc
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
    """
    Model representing a Locality in NMK CMS
    """

    abbreviation = models.CharField(
        max_length=2, help_text="Enter the Abbreviation of the Locality"
    )
    name = models.CharField(max_length=50, help_text="The name of the Locality.")

    class Meta:
        ordering = ["name"]

    def get_absolute_url(self):
        """
        Returns the url to access a particular Locality instance.
        """
        return reverse("locality-detail", args=[str(self.id)])

    def __str__(self):
        """
        String for representing the Model object (in Admin site etc.)
        """
        return "%s" % (self.name)
