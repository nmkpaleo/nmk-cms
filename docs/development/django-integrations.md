# Django Integrations

This companion guide documents deeper integrations that extend the baseline coding standards. Use it when working with shared utilities such as the merge engine, select widgets, or audit history.

## Table of Contents

1. [Merge Engine Integration](#merge-engine-integration)
2. [Select2 and History](#select2-and-history)

---

## Merge Engine Integration

- **Opt in with `MergeMixin`.** Inherit from `cms.merge.mixins.MergeMixin` on models that can participate in merges. Override `merge_fields` to define default strategies per field and `relation_strategies` when relations require bespoke handling (for example forcing a skip or custom callback).
- **Archive sources thoughtfully.** Provide an `archive_source_instance` implementation when the source record must be preserved. Serialise the source (for example via `cms.merge.serializers.serialize_instance`) before soft-deleting or exporting to an audit table so administrators can recover data if required.
- **Register defaults.** Use the merge registry to centralise configuration shared across admin workflows and programmatic merges:
  ```python
  from cms.merge.constants import MergeStrategy
  from cms.merge.registry import register_merge_rules

  register_merge_rules(
      MyModel,
      fields={
          "title": MergeStrategy.LAST_WRITE,
          "description": MergeStrategy.PREFER_NON_NULL,
      },
      relations={
          "members": "merge",
      },
  )
  ```
- **Review automated coverage.** The integration tests in `app/cms/tests/test_merge_engine.py`, `app/cms/tests/test_admin_merge.py`, and `app/cms/tests/test_merge_fuzzy_search.py` illustrate end-to-end expectations for field resolution, admin workflows, and the fuzzy candidate endpoint. Use them as templates when extending the engine to additional models.

---

## Select2 and History

- Use **django-select2** for searchable or async dropdowns; initialize via Django form widgets (`ModelSelect2Widget`).
- Register models with `HistoricalRecords()` from **django-simple-history** for audit tracking.
- Expose history views under authenticated routes and ensure collected static files include select2 and Font Awesome assets.
- Cover both select2 integration and history view logic in tests.
