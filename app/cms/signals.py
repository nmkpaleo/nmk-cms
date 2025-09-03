from django.db.models.signals import post_save, post_delete, pre_save, m2m_changed
from django.dispatch import receiver

from django.contrib.auth import get_user_model

from cms.models import (
    Accession,
    AccessionNumberSeries,
    AccessionReference,
    DrawerRegister,
    DrawerRegisterLog,
    Locality,
    Taxon,
)

User = get_user_model()

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


@receiver(pre_save, sender=DrawerRegister)
def log_status_change(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = DrawerRegister.objects.get(pk=instance.pk)
    except DrawerRegister.DoesNotExist:
        return
    if old.scanning_status != instance.scanning_status:
        DrawerRegisterLog.objects.create(
            drawer=instance,
            change_type=DrawerRegisterLog.ChangeType.STATUS,
            previous_status=old.scanning_status,
            new_status=instance.scanning_status,
        )


@receiver(m2m_changed, sender=DrawerRegister.scanning_users.through)
def log_user_change(sender, instance, action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if action == "post_clear":
        description = "Cleared users"
    else:
        usernames = list(
            User.objects.filter(pk__in=pk_set).values_list("username", flat=True)
        )
        if action == "post_add":
            description = f"Added users: {', '.join(usernames)}"
        else:
            description = f"Removed users: {', '.join(usernames)}"
    DrawerRegisterLog.objects.create(
        drawer=instance,
        change_type=DrawerRegisterLog.ChangeType.USER,
        new_status=instance.scanning_status,
        description=description,
    )


@receiver(m2m_changed, sender=DrawerRegister.localities.through)
def log_locality_change(sender, instance, action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if action == "post_clear":
        description = "Cleared localities"
    else:
        names = list(
            Locality.objects.filter(pk__in=pk_set).values_list("name", flat=True)
        )
        if action == "post_add":
            description = f"Added localities: {', '.join(names)}"
        else:
            description = f"Removed localities: {', '.join(names)}"
    DrawerRegisterLog.objects.create(
        drawer=instance,
        change_type=DrawerRegisterLog.ChangeType.USER,
        new_status=instance.scanning_status,
        description=description,
    )


@receiver(m2m_changed, sender=DrawerRegister.taxa.through)
def log_taxon_change(sender, instance, action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if action == "post_clear":
        description = "Cleared taxa"
    else:
        names = list(
            Taxon.objects.filter(pk__in=pk_set).values_list("taxon_name", flat=True)
        )
        if action == "post_add":
            description = f"Added taxa: {', '.join(names)}"
        else:
            description = f"Removed taxa: {', '.join(names)}"
    DrawerRegisterLog.objects.create(
        drawer=instance,
        change_type=DrawerRegisterLog.ChangeType.USER,
        new_status=instance.scanning_status,
        description=description,
    )
