from cms.models import SpecimenGeology


def create_specimen_geology(accession, earliest_geological_context,
                            latest_geological_context):
    """Create a SpecimenGeology instance.

    The previous version of this helper accepted a ``geological_context_type``
    argument which no longer exists on the ``SpecimenGeology`` model.  This
    implementation omits that argument and only saves the required fields.
    """
    return SpecimenGeology.objects.create(
        accession=accession,
        earliest_geological_context=earliest_geological_context,
        latest_geological_context=latest_geological_context,
    )
