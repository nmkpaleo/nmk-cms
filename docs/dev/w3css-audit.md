# W3.CSS Adoption Audit

## Methodology
- Reviewed the custom stylesheets under `app/cms/static/css/` and catalogued each selector that is not part of W3.CSS.
- Searched every HTML template in the repository to determine which templates still rely on the custom selector set.
- For each active usage, identified the closest W3.CSS component or utility class that can replace the bespoke styling. Where no direct analogue exists (e.g., screen-reader helpers), the selector is flagged for retention.
- Logged selectors that no longer appear in templates so they can be safely removed or replaced with W3.CSS during the refactor phase.

## `app/cms/static/css/style.css`

### Global helpers
- **Active selectors:** `.logo_image`, `.logout-form`, `.sr-only`, `.django-select2`, `.select2-container`, `.select2-selection`, and `.drag-handle` remain in `style.css` for logo sizing, logout form alignment, accessibility, Select2 layout, and drag affordance.
- **Templates:** The navigation include and drawer register list exercise these helpers; Select2 rules apply wherever the widget renders.
- **W3.CSS follow-up:** The logo sizing could move to a `w3-image` helper, and the logout form might adopt inline `style="margin:0"` to retire the class. `.sr-only` and the Select2 overrides fill gaps that W3.CSS does not address.

### Account entrance templates (`account/login.html`, `account/signup.html`, social login)
- **Status:** Login, signup, and the social provider prompt now rely solely on W3 containers, cards, and typography; all bespoke `.Login_*` selectors were removed from `style.css`.
- **Outcome:** No additional CSS is required beyond the global helpers above, keeping the entrance flows consistent with the rest of the W3-driven UI.

### Reports (`app/templates/reports/`)
- **Status:** Both OCR summary templates now wrap content with `w3-content w3-padding-32` and W3 card utilities, fully replacing the bespoke `.summary`, `.chart-container`, and `.message` helpers.
- **Outcome:** The shared `reports.css` bundle has been removed; the CMS base template no longer loads it, and report layouts depend solely on W3 classes.

### Drawer register drag handle
- **Custom selector:** `.drag-handle` enforces a grab cursor for reordering.
- **Template:** Applied in `cms/drawerregister_list.html` for the draggable rows.
- **W3.CSS consideration:** The affordance can shift to a `w3-button w3-round w3-light-grey` handle, keeping only the cursor override for clarity.

## `app/cms/static/css/merge_admin.css`
- **Status:** The bespoke merge stylesheet has been retired; the admin form template now uses W3 containers, cards, tables, and tag helpers directly, and the admin mixin no longer registers a CSS asset.
- **Dynamic UI:** Merge search results rendered via JavaScript also emit W3 cards and buttons, keeping the experience consistent without custom selectors.

## `app/cms/static/css/reports.css`
- **Status:** Retired; reporting pages now use W3 card, typography, and animation helpers directly in their templates, and the base template no longer references a dedicated stylesheet.
- **Guidance:** Future report templates should copy the W3 card blueprint and rely on W3 text utilities for contextual messaging to keep the CSS footprint minimal.

## Summary of recommended actions
1. **Navigation & dropdowns:** Rebuild using W3 bar/dropdown helpers and delete the corresponding custom selectors once verified. ✅
2. **Hero & marketing sections:** Swap bespoke flex/typography rules for W3 rows, typography, and button utilities. ✅
3. **Auth screens:** Transition to W3 cards/forms for consistent branding, keeping only the cursor or SR-only overrides that lack W3 equivalents. ✅
4. **Admin merge UI:** Monitor the W3-based merge workflow (template + JS) for additional accessibility or spacing tweaks that might warrant lightweight overrides instead of reintroducing a stylesheet.
5. **Reports:** Use the new W3 card blueprint when building future reporting pages to avoid resurrecting a dedicated stylesheet.
6. **Clean-up:** Delete unused selectors listed above to reduce maintenance, ensuring any future styling leans on W3 utilities first. ✅
