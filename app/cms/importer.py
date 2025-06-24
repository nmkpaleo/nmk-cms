from django.db import transaction
from tablib import Dataset
from .models import (
    Accession, AccessionRow, AccessionReference, NatureOfSpecimen,
    Identification, SpecimenGeology, Collection, Locality, Storage,
    Reference, Element, Person, GeologicalContext, User
)


def import_flat_file(file_obj):
    """Import a combined flat file covering multiple models."""
    dataset = Dataset()
    data = file_obj.read()
    dataset.load(data.decode("utf-8"), format="csv")

    with transaction.atomic():
        for row in dataset.dict:
            collection = Collection.objects.get(abbreviation=row.get("collection"))
            locality = Locality.objects.get(abbreviation=row.get("specimen_prefix"))
            user = None
            if row.get("accessioned_by"):
                user = User.objects.get(username=row.get("accessioned_by"))
            accession, _ = Accession.objects.get_or_create(
                collection=collection,
                specimen_prefix=locality,
                specimen_no=row.get("specimen_no"),
                defaults={
                    "instance_number": row.get("instance_number") or 1,
                    "accessioned_by": user,
                },
            )

            storage = None
            if row.get("storage"):
                storage = Storage.objects.get(area=row.get("storage"))
            accession_row, _ = AccessionRow.objects.get_or_create(
                accession=accession,
                specimen_suffix=row.get("specimen_suffix"),
                defaults={"storage": storage},
            )
            if storage:
                accession_row.storage = storage
                accession_row.save()

            if row.get("reference"):
                reference, _ = Reference.objects.get_or_create(citation=row.get("reference"))
                AccessionReference.objects.get_or_create(
                    accession=accession,
                    reference=reference,
                    defaults={"page": row.get("page")},
                )
            if row.get("element"):
                element, _ = Element.objects.get_or_create(name=row.get("element"))
                NatureOfSpecimen.objects.get_or_create(
                    accession_row=accession_row,
                    element=element,
                    defaults={
                        "side": row.get("side"),
                        "condition": row.get("condition"),
                        "verbatim_element": row.get("verbatim_element"),
                        "portion": row.get("portion"),
                        "fragments": row.get("fragments") or 0,
                    },
                )
            if any(row.get(k) for k in [
                "identified_by", "taxon", "date_identified",
                "identification_qualifier", "verbatim_identification",
                "identification_remarks",
            ]):
                person = None
                if row.get("identified_by"):
                    person, _ = Person.objects.get_or_create(last_name=row.get("identified_by"))
                ident_ref = None
                if row.get("reference"):
                    ident_ref, _ = Reference.objects.get_or_create(citation=row.get("reference"))
                Identification.objects.get_or_create(
                    accession_row=accession_row,
                    identified_by=person,
                    taxon=row.get("taxon"),
                    reference=ident_ref,
                    date_identified=row.get("date_identified") or None,
                    identification_qualifier=row.get("identification_qualifier"),
                    verbatim_identification=row.get("verbatim_identification"),
                    identification_remarks=row.get("identification_remarks"),
                )
            if row.get("earliest_geological_context") or row.get("latest_geological_context"):
                earliest = None
                latest = None
                if row.get("earliest_geological_context"):
                    earliest = GeologicalContext.objects.get(id=row.get("earliest_geological_context"))
                if row.get("latest_geological_context"):
                    latest = GeologicalContext.objects.get(id=row.get("latest_geological_context"))
                SpecimenGeology.objects.get_or_create(
                    accession=accession,
                    earliest_geological_context=earliest,
                    latest_geological_context=latest,
                    geological_context_type=row.get("geological_context_type"),
                )

    return dataset.height
