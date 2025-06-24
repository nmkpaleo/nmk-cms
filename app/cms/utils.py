from django.core.exceptions import ValidationError
from cms.models import Accession, AccessionNumberSeries

def generate_accessions_from_series(series_user, count, collection, specimen_prefix, creator_user=None):
    try:
        series = AccessionNumberSeries.objects.get(user=series_user, is_active=True)
    except AccessionNumberSeries.DoesNotExist:
        raise ValueError(f"No active accession number series found for user {series_user.username}.")

    start = series.current_number
    end = start + count - 1

    if end > series.end_at:
        raise ValueError("Not enough accession numbers left in this series.")

    accessions = []
    for number in range(start, end + 1):
        accessions.append(Accession(
            collection=collection,
            specimen_prefix=specimen_prefix,
            specimen_no=number,
            accessioned_by=series_user,
            instance_number=1,
            created_by=creator_user,
            modified_by=creator_user
        ))

    # ✅ Only update current_number if everything is valid
    series.current_number = end + 1
    series.save()

    # ✅ Save accessions individually to trigger signals
    for acc in accessions:
        acc.save()

    return accessions

def get_active_series_for_user(user):
    return AccessionNumberSeries.objects.filter(user=user, is_active=True).first()
