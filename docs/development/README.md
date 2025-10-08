# Coding Standards and Guidelines

This guide collects conventions that keep NMK CMS consistent and maintainable.  It will grow as the team documents additional patterns and architectural decisions.

## Merge Engine Integration

- **Opt in with `MergeMixin`**: Inherit from `cms.merge.mixins.MergeMixin` on models that can participate in merges. Override `merge_fields` to define default strategies per field and `relation_strategies` when relations require bespoke handling (for example forcing a skip or custom callback).
- **Archive sources thoughtfully**: Provide an `archive_source_instance` implementation when the source record must be preserved. Serialise the source (for example via `cms.merge.serializers.serialize_instance`) before soft-deleting or exporting to an audit table so administrators can recover data if required.
- **Register defaults**: Use the merge registry to centralise configuration shared across admin workflows and programmatic merges:

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

- **Review automated coverage**: The new integration tests in `app/cms/tests/test_merge_engine.py`, `app/cms/tests/test_admin_merge.py`, and `app/cms/tests/test_merge_fuzzy_search.py` illustrate end-to-end expectations for field resolution, admin workflows, and the fuzzy candidate endpoint. Use them as templates when extending the engine to additional models.

## Page Patterns

### List Pages
- **Layout**: Wrap each listing view in a `<div class="w3-container">` and use the W3.CSS grid (`w3-row`, `w3-col s12 m6 l6`, etc.) so headings and actions respond cleanly from mobile through large desktop breakpoints.
- **Heading Row**: Match the heading text to the navigation caption and keep the primary action (for example “New Accession”) on the same row, right aligned. Use a Font Awesome icon such as `fa-plus-circle` to reinforce the action.
- **Filters**: Provide a “Show/Hide Filters” toggle using W3 button styles and `fa-filter`. Group filter controls inside `w3-row-padding` blocks with responsive columns. Always include clear/apply buttons and reset to the list route when clearing.
- **Tables**: Wrap results in `w3-responsive` and use `w3-table-all w3-hoverable` for consistent stripes and borders. Include an `{% empty %}` clause so users see feedback when no rows match.
- **Pagination**: Paginate results at 10 items per page via the view’s `paginate_by` attribute so performance and usability stay predictable. The shared pagination component in `base_generic.html` already renders W3-styled controls with Font Awesome chevrons.
- **Permissions**: Hide creation links or restricted columns using the shared `has_group` filter or context flags so users never navigate to forbidden views.

### Detail Pages
_Build detail page guidance here. Capture expectations for heading structure, related record panels, and edit permissions._

### Forms and Wizards
_Document shared form layouts, validation messaging, and wizard navigation patterns._

## UI Components

### Filter Panels
- Use accordion toggles with `w3-animate-opacity` for smooth open/close behaviour.
- Keep form labels concise and rely on Django Filter widgets. Override widget CSS classes in the filter definition when a W3 input style is required.

### Icons and Media
- Font Awesome 6 is available globally—prefer the “solid” style for actions, toggles, and table controls.
- Use descriptive alternative text whenever embedding thumbnail images inside tables.

### Buttons and Links
- Base action buttons on `w3-button` with contextual colours (`w3-green` for creation, `w3-blue` for confirmation, `w3-gray` for resets). Pair each with an icon to signal intent quickly.

## Naming Conventions

### URLs
- Follow the pattern `<feature>_<action>` (e.g. `accession_list`, `fieldslip_detail`). Use hyphenated names only for multi-step flows that already exist (`accession-wizard`).
- Keep route names aligned with navigation captions so templates can reverse URLs predictably.

### Views
- Prefer class-based views named `<Model><Action>View` (for example, `AccessionListView`). Function-based views should use verbs that describe the action (`add_geology_to_accession`).
- Set `context_object_name` to the plural form for list views and singular for detail views to keep template variable names consistent.

### Templates and Context
- Store list templates under `cms/<feature>_list.html` and detail templates as `cms/<feature>_detail.html`.
- Pass capability flags such as `can_edit` from the view rather than recalculating permissions in templates.
- Ensure filter instances are provided in context with the key `filter` so templates can render `filter.form` consistently.

_Additional naming conventions (for example database fields, JavaScript helpers, or CSS utility classes) should be documented here as the project evolves._
