from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import AccessionReference

@receiver(post_save, sender=AccessionReference)
def update_accession_is_published_on_save(sender, instance, **kwargs):
    accession = instance.accession
    if not accession.is_published:
        accession.is_published = True
        accession.save(update_fields=['is_published'])

@receiver(post_delete, sender=AccessionReference)
def update_accession_is_published_on_delete(sender, instance, **kwargs):
    accession = instance.accession
    if not accession.accessionreference_set.exists():
        accession.is_published = False
        accession.save(update_fields=['is_published'])
