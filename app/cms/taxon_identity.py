"""Source-independent identity for catalogue taxa."""


def normalize_taxon_label(value):
    return " ".join((value or "").split())


def taxon_identity(name, rank):
    return f"{normalize_taxon_label(rank).lower()}:{normalize_taxon_label(name).lower()}"
