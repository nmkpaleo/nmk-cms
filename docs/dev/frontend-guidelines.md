# CMS Frontend Guidelines

_Last updated: 2025-10-24_

## Overview
The CMS frontend now relies almost entirely on W3.CSS utilities and semantic HTML5 landmarks. Every template extends `base_generic.html`, which loads the W3 stylesheet from the CDN, shared Font Awesome assets, and the small custom override bundle in `app/cms/static/css/style.css`. This document captures the patterns that must be preserved when building or updating templates.

### Core layout patterns
| Area | Key templates | W3.CSS primitives | Notes |
| --- | --- | --- | --- |
| Navigation shell | `base_generic.html` + `includes/navigation_links*.html` | `w3-bar`, `w3-bar-item`, `w3-dropdown-hover`, `w3-hide-large`, `w3-show` | Desktop and mobile menus share the same include logic. The logout control stays inside the navigation bar and requires the `.logout-form` override to remove default margins. |
| Landing / marketing | `index.html` | `w3-container`, `w3-row`, `w3-half`, `w3-padding-64`, `w3-button`, `w3-round-large` | Hero sections no longer use bespoke flexbox. Stick to W3 grid helpers for future promotional content. |
| List & filter views | `cms/*_list.html` variants | `w3-container`, `w3-card`, `w3-table-all`, `w3-responsive`, `w3-accordion`, `w3-hide-small` | Filter panels render inside `w3-card` accordions and expose django-filter forms styled with `w3-input` / `w3-select`. |
| Detail pages | `cms/*_detail.html` | `w3-card`, `w3-row-padding`, `w3-margin`, Font Awesome icons | History tables, related lists, and action toolbars all share the same W3 table/button vocabulary. |
| Forms & wizards | `cms/*_form.html`, `cms/qc/*wizard*.html`, `includes/base_form*.html` | `w3-card`, `w3-padding`, `w3-section`, `w3-button`, `w3-theme` palette | All form templates include the base form partial. Custom widgets (Select2, barcode inputs) inherit W3 wrappers and only require small CSS overrides documented below. |
| Admin merge UI | `admin/cms/merge/*.html`, `static/js/merge_admin.js` | `w3-container`, `w3-card-4`, `w3-responsive`, `w3-button`, `w3-badge` | Merge tables and comparison panes were rebuilt with W3 classes. JavaScript that injects rows must continue to emit the same class names for consistency. |
| Reports | `templates/reports/*.html` | `w3-content`, `w3-card`, `w3-padding-32`, `w3-panel`, `w3-pale-blue`/`w3-pale-green` | Charts and summary blocks no longer import a dedicated stylesheet. Reuse card and panel helpers for any new reporting screens. |
| Account entrance | `templates/account/login.html`, `templates/account/signup.html`, `templates/socialaccount/snippets/login.html` | `w3-display-container`, `w3-card`, `w3-padding`, `w3-margin`, `w3-button`, `w3-round` | The allauth templates now mirror the CMS look and feel while relying purely on W3 utilities. |
| Inventory workflows | `templates/inventory/start.html`, `templates/inventory/session.html` | `w3-row`, `w3-col`, `w3-card`, `w3-modal`, `w3-pale-*` status helpers | Inline JavaScript toggles W3 contextual classes to reflect scan states; do not reintroduce bespoke CSS for these alerts. |

## Template guidelines

1. **Extend the base layout.** All new templates should inherit from `base_generic.html` to obtain navigation, asset loading, and the responsive grid meta tags.
2. **Use semantic regions.** Continue to wrap primary content in `<main>`, logical sections in `<section>`/`<article>`, and supporting content in `<aside>`/`<footer>`.
3. **Leverage W3 grids before custom CSS.** `w3-row-padding` and `w3-col` (or `w3-half`, `w3-third`, etc.) cover most layout needs. When the design calls for alignment tweaks, prefer W3 spacing utilities (`w3-margin`, `w3-padding`) over hand-written rules.
4. **Buttons and links.** Use `w3-button` combined with palette classes (`w3-theme`, `w3-teal`, `w3-white`, `w3-border`) for all calls to action. Rounded buttons should add `w3-round` or `w3-round-large` instead of bespoke border radii.
5. **Forms.** Django form widgets should receive W3 classes via either the shared base form include or widget `attrs`. Inputs use `w3-input`, selects use `w3-select`, and groups should sit inside `w3-section` or `w3-margin-bottom` containers. Preserve ARIA attributes and label associations provided by Django.
6. **Tables.** Data tables should combine `w3-table-all` with `w3-striped`, `w3-hoverable`, and `w3-responsive` as appropriate. Pagination controls reuse the navigation button pattern with `w3-bar` wrappers.
7. **Messages and alerts.** Use W3 panel helpers (`w3-panel`, `w3-pale-green`, `w3-border`) for flash messages, validation summaries, or background highlights.
8. **Icons.** Font Awesome 6 is available globally. Use the standard `<i class="fa-solid fa-icon">` markup and avoid inline SVG unless the icon is missing from FA.

## Custom CSS inventory
The shared stylesheet `app/cms/static/css/style.css` intentionally remains small. Only the following helpers are allowed:

- `.logo_image` – constrains the navigation logo width so it fits within the bar.
- `.logout-form` – removes default margins around the logout button’s form wrapper so it aligns with bar items.
- `.sr-only` – provides an accessible screen-reader-only helper that W3.CSS does not supply.
- `.django-select2`, `.select2-container`, `.select2-selection`, `.select2-dropdown` – ensure Select2 widgets span full width and stack above modals or dropdowns.
- `.drag-handle` – keeps the grab cursor for drag-to-reorder handles; JavaScript toggles this on drawer lists.

Do not add new selectors without first checking whether a W3 utility or an existing helper can cover the requirement. If a new override is unavoidable, document the rationale directly above the rule and update this guideline.

## JavaScript expectations
Certain scripts assume W3 classes are present:

- `static/javascript.js` toggles `w3-show` and `w3-hide` to open the mobile navigation panel.
- `static/js/merge_admin.js` generates search results using `w3-card-4`, `w3-padding`, and `w3-button` classes. Any markup changes must update both the template and script.
- Inventory scanning scripts add contextual classes such as `w3-pale-green` to status elements. Keep those hooks stable.

## Testing coverage
Template regression tests live in `app/cms/tests/` and verify that W3 classes render as expected:

- `test_navigation.py` asserts the navigation bar structure and mobile toggle behaviour.
- `test_filter_widgets.py` ensures django-filter widgets expose W3 form classes.
- `test_account_templates.py` checks the login and signup templates for the expected card and button classes.

Add similar assertions when creating new templates that depend on W3-specific structure.

## Future enhancements
- Extract the repeated filter accordion into a reusable include to reduce duplication across list templates.
- Publish example snippets for common layouts (cards, tables, modals) so contributors can copy the sanctioned markup.
- Audit remaining JavaScript-driven DOM injections to ensure they emit the same class names as the server-rendered templates.
