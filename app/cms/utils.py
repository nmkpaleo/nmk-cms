from django.core.exceptions import ValidationError
from cms.models import Accession, AccessionNumberSeries

def generate_accessions_from_series(user, count, collection=None, specimen_prefix=None):
    series = AccessionNumberSeries.objects.filter(user=user, is_active=True).first()
    if not series:
        raise ValidationError(f"No active accession number series found for user {user.username}.")

    numbers = series.get_next_batch(count)

    accessions = [
        Accession(
            specimen_no=num,
            accessioned_by=user,
            collection=collection,
            specimen_prefix=specimen_prefix,
            instance_number=1
        )
        for num in numbers
    ]

    return Accession.objects.bulk_create(accessions)