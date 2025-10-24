# W3.CSS Adoption Audit

## Methodology
- Reviewed the custom stylesheets under `app/cms/static/css/` and catalogued each selector that is not part of W3.CSS.
- Searched every HTML template in the repository to determine which templates still rely on the custom selector set.
- For each active usage, identified the closest W3.CSS component or utility class that can replace the bespoke styling. Where no direct analogue exists (e.g., screen-reader helpers), the selector is flagged for retention.
- Logged selectors that no longer appear in templates so they can be safely removed or replaced with W3.CSS during the refactor phase.

## `app/cms/static/css/style.css`

### Global helpers
- **Active selectors:** `.logo_image`, `.logout-form`, and `.sr-only` remain in `style.css` to size the NMK logo, remove default margins on the logout form, and provide a reusable screen-reader utility.【F:app/cms/static/css/style.css†L5-L34】
- **Templates:** The navigation include renders all three helpers.【F:app/cms/templates/base_generic.html†L40-L68】【F:app/cms/templates/includes/navigation_links_inner.html†L10-L49】
- **W3.CSS follow-up:** The logo sizing could move to an inline `style` or `w3-image` helper, and the logout form can switch to `class="w3-margin-0"` to eliminate bespoke CSS. `.sr-only` continues to fill an accessibility gap not covered by W3.CSS.

### Account entrance templates (`account/login.html`, `account/signup.html`, social login)
- **Custom selectors:** `.Login_page`, `.Login_box`, `.login-h1`, `.login-profile`, `.signup-text`, `.login-Sign_In_With-h4`, and the input/button overrides scoped under `.Login_box` persist to preserve the existing entrance design.【F:app/cms/static/css/style.css†L36-L140】
- **Templates:** Login and signup flows render the namespace, along with the social login partial.【F:app/templates/account/login.html†L9-L104】【F:app/templates/account/signup.html†L8-L63】【F:app/templates/socialaccount/snippets/login.html†L12-L16】
- **W3.CSS alternatives:** Wrap the forms in `w3-container w3-padding-64 w3-card-4` structures, lean on `w3-input`/`w3-button w3-block` for controls, and re-create the profile badge with `w3-circle w3-border`. Once those templates migrate, the scoped overrides can be retired.

### Reports (`app/templates/reports/`)
- **Status:** Both OCR summary templates now wrap content with `w3-content w3-padding-32` and add `w3-card w3-round-large` framing to charts and tables, replacing the bespoke `.container` and Bootstrap-derived classes.【F:app/templates/reports/media_report.html†L9-L33】【F:app/templates/reports/accession_distribution.html†L7-L34】
- **Next steps:** Gradually fold the remaining `reports.css` shadows and typography into W3 equivalents (`w3-animate-opacity`, `w3-text-grey`, etc.) until the dedicated stylesheet is no longer required.

### Form error styling
- **Custom selector:** `ul.errorlist.nonfield` remains, but is now scoped to `.Login_box` so only the entrance flows receive the bespoke alert styling.【F:app/cms/static/css/style.css†L89-L101】
- **W3.CSS alternative:** Replace the block with a `w3-panel w3-pale-red w3-leftbar w3-border-red` wrapper once the login/signup screens adopt the shared form partials.

### Drawer register drag handle
- **Custom selector:** `.drag-handle` enforces a grab cursor for reordering.【F:app/cms/static/css/style.css†L150-L156】
- **Template:** Applied in `cms/drawerregister_list.html` for the draggable rows.【F:app/cms/templates/cms/drawerregister_list.html†L70-L86】
- **W3.CSS consideration:** The affordance can shift to a `w3-button w3-round w3-light-grey` handle, keeping only the cursor override for clarity.

## `app/cms/static/css/merge_admin.css`
- **Custom selectors:** `.merge-admin*` namespace controls layout, cards, badges, tables, and error messaging for the merge UI.【F:app/cms/static/css/merge_admin.css†L1-L131】
- **Templates:** Exclusively used by `app/cms/templates/admin/cms/merge/merge_form.html`.【F:app/cms/templates/admin/cms/merge/merge_form.html†L12-L153】
- **W3.CSS alternatives:**
  - Wrap the entire interface in `w3-container w3-padding-32` instead of fixed `max-width` containers.
  - Convert selection grids and cards to `w3-row-padding` with `w3-third` / `w3-half` columns and `w3-card-4 w3-round-large` articles.
  - Replace badge styling with `w3-tag w3-round w3-small`.
  - Use `w3-panel w3-pale-red` for error blocks and `w3-table-all w3-striped` for the comparison table.
  - Leverage `w3-bar w3-right` for action button groups instead of flexbox gaps.

## `app/cms/static/css/reports.css`
- **Custom selectors:** Body font/background overrides, `.summary`, `.chart-container`, `.message`, and fade-in animation styling.【F:app/cms/static/css/reports.css†L4-L58】
- **Templates:** Applied in `app/templates/reports/media_report.html` for OCR metrics and embedded charts.【F:app/templates/reports/media_report.html†L7-L35】
- **W3.CSS alternatives:**
  - Replace `.summary` and `.chart-container` cards with `w3-card-4 w3-round-large w3-padding-24 w3-white` blocks.
  - Use `w3-text-grey`, `w3-large`, and `w3-center` to style text instead of bespoke typography.
  - Swap the body background and font settings for W3 theme classes (`w3-light-grey`, `w3-theme-l5`) applied on the `<body>` via template blocks.
  - Optional: reproduce the fade-in effect with `w3-animate-opacity` to avoid custom keyframes.

## Summary of recommended actions
1. **Navigation & dropdowns:** Rebuild using W3 bar/dropdown helpers and delete the corresponding custom selectors once verified.
2. **Hero & marketing sections:** Swap bespoke flex/typography rules for W3 rows, typography, and button utilities.
3. **Auth screens:** Transition to W3 cards/forms for consistent branding, keeping only the cursor or SR-only overrides that lack W3 equivalents.
4. **Admin merge UI:** Map each layout construct to W3 cards, grids, tables, and panels, significantly reducing `merge_admin.css`.
5. **Reports:** Convert report wrappers and cards to W3 components and remove the dedicated `reports.css` once templates rely solely on W3 classes.
6. **Clean-up:** Delete unused selectors listed above to reduce maintenance, ensuring any future styling leans on W3 utilities first.
