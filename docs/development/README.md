# Coding Standards and Guidelines

This guide collects conventions that keep NMK CMS consistent and maintainable. It will grow as the team documents additional patterns and architectural decisions.

---

## Technology Stack and Template Requirements

### HTML5 and Base Templates
- Use semantic HTML5 elements (`<header>`, `<main>`, `<section>`, `<article>`, `<aside>`, `<footer>`).
- Always include `<!DOCTYPE html>`, `<meta charset="utf-8">`, and `<meta name="viewport" content="width=device-width, initial-scale=1">` in `base_generic.html`.
- Compose page templates by extending `base_generic.html` and populating semantic blocks (`<main>`, `<nav>`, etc.).
- Extract reusable components into `{% include %}` templates for maintainability.

### W3.CSS Styling
- Load W3.CSS globally from the official CDN in the base template.
- Prefer W3.CSS utility classes (`w3-container`, `w3-row`, `w3-col`, etc.) before introducing custom CSS.
- Define custom overrides in a separate stylesheet loaded **after** W3.CSS.

### Font Awesome Icons
- Font Awesome 6 is globally available; prefer the “solid” style for actions and controls.
- Use `<i>` or `<span>` elements with `aria-hidden="true"` and provide visually hidden text when icons convey meaning.
- Maintain consistent icon use (e.g., `fa-plus` for “create,” `fa-edit` for “edit”).

---

## Django Integrations

### Merge Engine Integration
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

### Select2 and History
- Use **django-select2** for searchable or async dropdowns; initialize via Django form widgets (`ModelSelect2Widget`).
- Register models with `HistoricalRecords()` from **django-simple-history** for audit tracking.
- Expose history views under authenticated routes and ensure collected static files include select2 and Font Awesome assets.
- Cover both select2 integration and history view logic in tests.

---

## Page Patterns

### List Pages
- **Layout**: Wrap each listing view in a `<div class="w3-container">` and use the W3.CSS grid (`w3-row`, `w3-col s12 m6 l6`, etc.) so headings and actions respond cleanly from mobile through large desktop breakpoints.
- **Heading Row**: Match the heading text to the navigation caption and keep the primary action (for example “New Accession”) on the same row, right aligned. Use a Font Awesome icon such as `fa-plus-circle` to reinforce the action.
- **Filters**: Provide a “Show/Hide Filters” toggle using W3 button styles and `fa-filter`. Group filter controls inside `w3-row-padding` blocks with responsive columns. Always include clear/apply buttons and reset to the list route when clearing.
- **Tables**: Wrap results in `w3-responsive` and use `w3-table-all w3-hoverable` for consistent stripes and borders. Include an `{% empty %}` clause so users see feedback when no rows match.
- **Pagination**: Paginate results at 10 items per page via the view’s `paginate_by` attribute so performance and usability stay predictable. The shared pagination component in `base_generic.html` already renders W3-styled controls with Font Awesome chevrons.
- **Permissions**: Hide creation links or restricted columns using the shared `has_group` filter or context flags so users never navigate to forbidden views.

### Detail Pages
- Extend the “Detail View” archetype: a single-entity page showing record metadata and related contextual actions.
- When appropriate, combine with sub-lists or tabs to display related items (e.g., linked records or history logs).

### Common Archetypes
| Archetype | Description | Example Use |
|-----------|-------------|-------------|
| **List View** | Tabular or card-based collections with filtering, sorting, and pagination. | “Project List” page with select2 filters. |
| **Detail View** | Shows a single record’s full details. | “Project Detail” form. |
| **Master-Detail** | Combines detail with related lists or tabs. | “Project + Tasks” combined page. |
| **Create/Edit Form** | For creating or updating entities; may use wizards. | “New Task” form. |
| **Dashboard View** | Aggregates metrics or shortcuts. | Admin landing page. |
| **History View** | Surfaces audit logs from django-simple-history. | “Project History” page. |

### Forms and Wizards
- Use W3.CSS form styles for layout and spacing.
- Leverage Django’s built-in validation alongside HTML5 attributes.
- Include client-side validation messages where appropriate.

---

## UI Components

### Filter Panels
- Use accordion toggles with `w3-animate-opacity` for smooth open/close behaviour.
- Keep form labels concise and rely on Django Filter widgets. Override widget CSS classes in the filter definition when a W3 input style is required.

### Icons and Media
- Font Awesome 6 is available globally—prefer the “solid” style for actions, toggles, and table controls.
- Use descriptive alternative text whenever embedding thumbnail images inside tables.

### Buttons and Links
- Base action buttons on `w3-button` with contextual colours (`w3-green` for creation, `w3-blue` for confirmation, `w3-gray` for resets). Pair each with an icon to signal intent quickly.

---

## Testing Expectations

- Write tests under each app’s `tests` module using `django.test.TestCase` or `pytest`.
- Cover:
  - View logic and template context.
  - HTML5 and W3.CSS structure.
  - Select2 widgets and history views.
- Use `Client` or `RequestFactory` to assert expected markup and accessibility attributes.

---

## Responsive and Accessibility Guidelines

- Design mobile-first layouts using W3.CSS breakpoints:
  - Phones: 0–600px
  - Tablets: 601–992px
  - Laptops: 993–1366px
  - Desktops: 1367px+
- Maintain accessible color contrast (WCAG AA).
- Provide ARIA attributes (`aria-label`, `aria-live`, etc.) especially for dynamic widgets.
- Verify layouts across devices using responsive previews or emulators.

---

## Template and Asset Structure

1. Shared `base_generic.html` loads HTML5 boilerplate, W3.CSS, Font Awesome, and scripts.
2. App templates extend `base_generic.html` and keep reusable sections in includes.
3. Static files reside in `app/static/<app_label>/`.
4. Collect static assets via:
   ```bash
   python manage.py collectstatic
   ```

---

## Code Comments and Documentation

- Explain *why* a non-obvious implementation exists rather than restating what code does.
- Document integrations like select2 or simple-history inline.
- Remove outdated comments during refactors.

---

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
