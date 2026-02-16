# Coding Standards and Guidelines

This guide collects conventions that keep NMK CMS consistent and maintainable. It will grow as the team documents additional patterns and architectural decisions.

## How to Use This Guide

- **Start here for day-to-day expectations.** Each section outlines baseline standards for Python code, Django views and templates, accessibility, and quality assurance.
- **Consult dedicated integration notes as needed.** Deep-dive guidance for framework add-ons (e.g., merge tooling or select widgets) now lives in separate documents such as [Django Integrations](./django-integrations.md).
- **Review upgrade guides before major version bumps.** Follow the [Django 5.2 upgrade playbook](./django-52-upgrade.md) for configuration expectations, behavioural shifts, and rollback steps.
- **Follow the release process for production deployments.** Use the [release checklist](./release-checklist.md) for `main` -> `prod` merges, automated tags, and GitHub Releases.
- **Propose additions when new patterns emerge.** Capture decisions in pull requests so this guide evolves alongside the product.

## Table of Contents

1. [Python and Django Coding Practices](#python-and-django-coding-practices)
2. [Template and Front-End Standards](#template-and-front-end-standards)
3. [Page Patterns](#page-patterns)
4. [UI Components](#ui-components)
5. [Testing Expectations](#testing-expectations)
6. [Responsive and Accessibility Guidelines](#responsive-and-accessibility-guidelines)
7. [Template and Asset Structure](#template-and-asset-structure)
8. [Documentation and Collaboration Practices](#documentation-and-collaboration-practices)

---

## Python and Django Coding Practices

- **Follow PEP 8 and favour readability.** Keep modules focused, name things descriptively, and prefer explicit imports. Use type hints for new code to aid editor tooling and reviews.
- **Keep business logic close to the model layer.** Prefer model methods, services, or domain utilities over view-level monoliths so behaviour is reusable across forms, admin actions, and APIs.
- **Optimise database access.** Use `select_related`/`prefetch_related` for relationship-heavy queries, paginate long lists, and avoid raw SQL unless there is a measured performance need.
- **Validate through Django forms and serializers.** Avoid duplicating validation logic in views; lean on Django’s form/serializer cleaning methods for consistent error messages and security.
- **Respect configuration boundaries.** Store secrets in environment variables, keep default settings safe for local development, and document any new settings in release notes.
- **Log meaningfully and handle errors gracefully.** Capture actionable details, prefer structured logging where available, and present user-friendly feedback on failure.

---

## Template and Front-End Standards

### Technology Stack and Template Requirements

- **Framework and Environment Versions**
  - **Python:** 3.10-slim
  - **Django:** 5.2 LTS

### HTML5 and Base Templates

- Use semantic HTML5 elements (`<header>`, `<main>`, `<section>`, `<article>`, `<aside>`, `<footer>`).
- Always include `<!DOCTYPE html>`, `<meta charset="utf-8">`, and `<meta name="viewport" content="width=device-width, initial-scale=1">` in `base_generic.html`.
- Compose page templates by extending `base_generic.html` and populating semantic blocks (`<main>`, `<nav>`, etc.).
- Extract reusable components into `{% include %}` templates for maintainability.

#### Base Template Requirements

- The `base_generic.html` file must:
  - Include the HTML5 boilerplate (`<!DOCTYPE html>`, `<html lang="en">`, `<meta charset="utf-8">`, `<meta name="viewport" content="width=device-width, initial-scale=1">`).
  - Load global assets in the `<head>` section: W3.CSS (from CDN), Font Awesome (from CDN), and project-wide JavaScript files.
  - Define common template blocks:
    - `{% block title %}` for page titles.
    - `{% block content %}` as the main body area.
    - `{% block extra_head %}` and `{% block extra_scripts %}` for per-page additions.
  - Contain semantic wrapper elements (`<header>`, `<main>`, `<footer>`).
  - Include shared navigation (`{% include 'partials/navbar.html' %}` or equivalent) when applicable.
- All feature templates must extend this base to ensure global consistency.

### W3.CSS Styling

- Load W3.CSS globally from the official CDN in the base template.
- Prefer W3.CSS utility classes (`w3-container`, `w3-row`, `w3-col`, etc.) before introducing custom CSS.
- Define custom overrides in a separate stylesheet loaded **after** W3.CSS.

#### W3.CSS Overrides and Custom Styling

- Custom styles should be minimal and placed in `static/css/custom.css`, loaded **after** W3.CSS in the base template.
- Prefix all custom classes with a project-specific namespace (e.g., `.nmk-`) to avoid conflicts with W3.CSS.
- Avoid overriding W3.CSS class definitions directly; instead, extend them using additional class selectors.
- When overriding is necessary (e.g., for branding colors), document the rationale in comments within `custom.css`.
- Limit inline styles to debugging or prototyping only.

### Font Awesome Icons

- Font Awesome 6 is globally available; prefer the “solid” style for actions and controls.
- Use `<i>` or `<span>` elements with `aria-hidden="true"` and provide visually hidden text when icons convey meaning.
- Maintain consistent icon use (e.g., `fa-plus` for “create,” `fa-edit` for “edit”).

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
- Add regression tests when fixing bugs or refining complex behaviours (for example, pagination edge cases or permission rules).
- Keep fixtures lightweight; prefer factory functions or `ModelFactory` helpers when available.

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
- Ensure interactive controls are keyboard navigable and announce state changes for assistive technologies.

---

## Template and Asset Structure

1. Shared `base_generic.html` loads HTML5 boilerplate, W3.CSS, Font Awesome, and scripts.
2. App templates extend `base_generic.html` and keep reusable sections in includes.
3. Static files reside in `app/static/<app_label>/`.
4. Collect static assets via:
   ```bash
   python manage.py collectstatic
   ```
5. `base_generic.html` serves as the canonical base template for all apps to maintain consistency.

---

## Documentation and Collaboration Practices

- Update inline documentation, docstrings, or ADRs when you introduce noteworthy patterns.
- Reference relevant tickets in commit messages and keep pull requests focused on one change set.
- Surface decisions about migrations, data scripts, or integration changes in release notes or the `docs/` directory to aid future onboarding.
- Pair complex refactors with before/after screenshots or architectural diagrams when visual context helps reviewers.
