from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from cms.models import Accession, AccessionNumberSeries, AccessionReference

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

@receiver(post_save, sender=Accession)
def check_series_completion(sender, instance, **kwargs):
    user = instance.accessioned_by
    if not user:
        return

    active_series = AccessionNumberSeries.objects.filter(user=user, is_active=True).first()
    if not active_series:
        return

    # Count how many accession numbers fall within this series
    used_count = Accession.objects.filter(
        accessioned_by=user,
        specimen_no__gte=active_series.start_from,
        specimen_no__lte=active_series.end_at
    ).count()

    total_slots = active_series.end_at - active_series.start_from + 1

    if used_count >= total_slots:
        active_series.is_active = False
        active_series.save()