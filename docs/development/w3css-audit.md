# W3.CSS Adoption Audit

_Last updated: 2025-10-24_

## Methodology
- Review each stylesheet under `app/cms/static/css/` and note selectors that are not part of stock W3.CSS.
- Trace every selector through the Django templates to confirm whether it is still exercised after the refactor.
- For active selectors, identify the equivalent W3 utility or component that now covers the use case.
- Flag any selectors that must remain because W3.CSS lacks the necessary behaviour.

## Current CSS footprint
Only one local stylesheet remains: `app/cms/static/css/style.css`. Its contents fall into five groups:

| Selector(s) | Purpose | Templates / scripts | W3.CSS coverage |
| --- | --- | --- | --- |
| `.logo_image` | Constrains the navigation logo dimensions so it fits inside the W3 bar. | `base_generic.html` navigation include. | No direct alternative; retain until the asset is resized or replaced with an inline SVG using `w3-image`. |
| `.logout-form` | Removes default margins from the logout form that renders inside the navigation bar. | Shared navigation include. | Could be replaced with inline `style="margin:0"`, but the class keeps markup cleaner. |
| `.sr-only` | Screen-reader-only helper for hidden labels and instructions. | Login templates, navigation skip links, filter toggles. | W3.CSS does not ship an equivalent helper, so keep this rule. |
| `.django-select2`, `.select2-container`, `.select2-selection`, `.select2-dropdown` | Forces Select2 widgets to fill their containers and stack above modals/menus. | Any form that renders Select2 widgets. | W3.CSS covers general input spacing but not the Select2 integration; retain these rules. |
| `.drag-handle` | Provides a grab cursor for draggable drawer rows. | `cms/drawerregister_list.html`. | W3 cursor helpers are insufficient; keep the rule but prefer W3 button styling for the handle body. |

All other bespoke stylesheets—`merge_admin.css` and `reports.css`—were removed. Their selectors were replaced with the W3 equivalents summarised below.

### Areas converted entirely to W3 utilities
- **Navigation and layout:** `base_generic.html` uses `w3-bar` and `w3-dropdown-*` helpers for both desktop and mobile navigation states. The mobile toggle script flips the `w3-show` class rather than adding inline styles.
- **Landing page:** The marketing hero in `index.html` now uses `w3-container`, `w3-row`, and `w3-half` instead of custom flexbox rules.
- **List and detail pages:** All CMS list templates render filter accordions with `w3-card` wrappers and tables with `w3-table-all` plus responsive helpers. Detail pages use `w3-card` stacks and Font Awesome headers.
- **Forms:** Shared form includes apply `w3-input`, `w3-select`, and `w3-button` classes, eliminating the need for `.template_form_*` selectors.
- **Authentication:** Login, signup, and social login templates rely exclusively on `w3-card`, `w3-padding`, and `w3-button` classes.
- **Merge admin:** Templates and `static/js/merge_admin.js` output `w3-card-4` comparison blocks, `w3-responsive` tables, and W3 buttons in place of the retired merge stylesheet.
- **Reports:** Reporting templates wrap charts and messages with `w3-content`, `w3-card`, and `w3-panel` helpers instead of the old `.summary` and `.chart-container` rules.

### Retained selectors requiring review before removal
- `.logo_image` – evaluate whether the navigation logo asset can be updated to remove the size constraint.
- `.logout-form` – consider replacing with inline style if the markup changes significantly.
- `.sr-only` – maintain indefinitely for accessibility.
- `.django-select2` / `.select2-*` – keep while Select2 remains the widget of choice.
- `.drag-handle` – keep the cursor override but prefer W3 button classes for any new drag handles.

## Verification
Automated tests cover the critical W3 structures:
- Navigation tests ensure the presence of `w3-bar` and mobile toggle classes.
- Filter widget tests confirm that django-filter forms render W3 input and select classes.
- Account template tests assert the card layout used for login and signup views.

Developers should run the Django test suite after template updates to confirm these checks stay green. If new components rely on specific W3 classes, add similar tests to prevent regressions.

## Next steps
1. Continue consolidating shared template fragments (e.g., filter accordions) so W3 markup lives in one place.
2. Document copy-ready snippets for cards, accordions, and modals in the developer docs to encourage consistent structure.
3. Periodically audit Select2 usage; if the dependency is replaced, remove the related overrides from `style.css`.
