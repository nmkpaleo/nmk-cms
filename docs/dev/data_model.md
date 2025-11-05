# Locality Geological Time Model Notes

_Last updated: 2025-10-24_

## Field Summary
- **Model:** `app.cms.models.Locality`
- **Field:** `geological_times`
- **Type:** `models.JSONField` storing a list of geological time abbreviations (`M`, `Pi`, `Pe`, `H`).
- **Choices:** Implemented via `Locality.GeologicalTime`, which maps abbreviations to labels:
  | Abbreviation | Label |
  | --- | --- |
  | `M` | Miocene |
  | `Pi` | Pliocene |
  | `Pe` | Pleistocene |
  | `H` | Holocene |

## Validation & Normalisation
- Model `clean()` ensures the stored value is a list containing only defined abbreviations.
- Duplicate selections are removed while preserving the original order.
- Form handling (`LocalityForm`) and import/export widgets accept either abbreviations or labels and always persist abbreviations.
- django-simple-history automatically captures changes to `geological_times` for traceability.

## Querying & Filtering
- `LocalityFilter` exposes a `MultipleChoiceFilter` on geological times, building `JSONField` `contains` queries so each selected value is treated independently.
- Admin search normalises input and matches both abbreviations and labels before applying JSON containment filters.
- Aggregations (such as accession counts) can be chained on the queryset because the field is stored as a JSON array of short strings.

## Presentation
- Public and staff-facing templates render geological time **labels** joined with `/`. Tooltips (for example on the locality detail view) expose the underlying abbreviations when needed.
- The printable locality report renders two columns of locality data and ends with an abbreviation legend derived from the enum choices.

## Import/Export
- `LocalityResource` defines a `GeologicalTimesWidget` that:
  - Accepts `/`-delimited abbreviations or labels during import.
  - Exports joined labels for readability.
  - Normalises lazily translated labels to plain strings before validation and export to avoid admin CSV errors.

## Testing Considerations
- See `docs/dev/testing.md` for the specific pytest modules covering validation, filtering, view rendering, and import/export helpers for geological time support.
