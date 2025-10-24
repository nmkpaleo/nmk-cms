# W3.CSS Adoption Audit

## Methodology
- Reviewed the custom stylesheets under `app/cms/static/css/` and catalogued each selector that is not part of W3.CSS.
- Searched every HTML template in the repository to determine which templates still rely on the custom selector set.
- For each active usage, identified the closest W3.CSS component or utility class that can replace the bespoke styling. Where no direct analogue exists (e.g., screen-reader helpers), the selector is flagged for retention.
- Logged selectors that no longer appear in templates so they can be safely removed or replaced with W3.CSS during the refactor phase.

## `app/cms/static/css/style.css`

### Global navigation (`base_generic.html`)
- **Custom selectors:** `.main-navbar`, `.nav-logo`, `.logo_image`, `.nav-toggle`, `.nav-links`, `.nav-item`, `.nav-right`, `.nav-text`, `.nav-link`, `.nav-button`, `.logout-form`, `.nav-dropdown`, `.nav-dropdown-menu` plus responsive media queries.【F:app/cms/static/css/style.css†L11-L188】
- **Templates:** Primary site navigation still renders these classes in `base_generic.html`.【F:app/cms/templates/base_generic.html†L43-L106】
- **W3.CSS alternatives:**
  - Replace bespoke flex layout with `w3-bar`, `w3-bar-item`, and `w3-right` to handle alignment instead of `.nav-links` / `.nav-item` flex rules.
  - Use `w3-button w3-round-large w3-theme` (or the project theme palette) for CTA styles in place of `.nav-button`.
  - Swap `.nav-dropdown` structures for the W3 dropdown pattern: `w3-dropdown-hover`/`w3-dropdown-click` with `.w3-dropdown-content w3-card-4`.
  - Apply `w3-hide-small` / `w3-hide-medium` utilities for responsive hide/show logic instead of custom media queries.
  - Keep `.sr-only` for screen-reader-only copy; W3.CSS does not ship an equivalent helper and accessibility should not regress.【F:app/cms/static/css/style.css†L143-L153】

### Landing hero (`index.html`)
- **Status:** Rebuilt with W3 layout, typography, and button utilities; bespoke hero selectors have been removed from `style.css`.
- **Templates:** The landing hero now uses `w3-row-padding`, `w3-col`, `w3-xxxlarge`, and `w3-button` helpers to deliver the responsive layout and CTA styling.【F:app/cms/templates/index.html†L6-L21】
- **Follow-up:** None required unless additional marketing sections are added; reuse the same W3 patterns before introducing new custom CSS.

### Legacy Bootstrap-like container usage (reports)
- **Custom selector:** `.container` sets a fixed width and center alignment for report templates.【F:app/cms/static/css/style.css†L375-L383】
- **Templates:** `app/templates/reports/media_report.html` and `app/templates/reports/accession_distribution.html` pull in the class (and additional Bootstrap spacing helpers).【F:app/templates/reports/media_report.html†L9-L35】【F:app/templates/reports/accession_distribution.html†L7-L52】
- **W3.CSS alternatives:** Replace `.container` / Bootstrap margin utilities with `w3-content w3-padding-32` (outer wrapper) and `w3-margin-top` / `w3-margin-bottom` / `w3-center` for spacing. W3 `w3-card` / `w3-round` utilities can substitute the inline box shadows defined alongside the container.

### Account entrance templates (`account/login.html`, `account/signup.html`, social login)
- **Custom selectors:** `.Login_page`, `.Login_box`, `.login-h1`, `.login-profile`, `.signup-text`, `.login-Sign_In_With-h4` and related form input overrides.【F:app/cms/static/css/style.css†L724-L887】
- **Templates:** Login and signup flows render the classes, along with the social login partial.【F:app/templates/account/login.html†L9-L104】【F:app/templates/account/signup.html†L8-L63】【F:app/templates/socialaccount/snippets/login.html†L12-L16】
- **W3.CSS alternatives:**
  - Wrap forms in `w3-display-container` + `w3-display-middle` or `w3-container w3-padding-64 w3-card-4` to achieve the centered modal feel.
  - Replace heading styles with `w3-xlarge w3-center w3-text-theme`.
  - Use `w3-circle` and `w3-border` helpers for the profile icon container, or rely on `w3-card` for depth.
  - Style form controls with `w3-input w3-border w3-round-large` and CTA buttons with `w3-button w3-block w3-theme` to retire the custom gradients and shadows.
  - For helper text, use `w3-text-grey` and `w3-small` utilities; hide remember-me via template logic instead of CSS if necessary.

### Drawer register drag handle
- **Custom selector:** `.drag-handle` enforces a grab cursor for reordering.【F:app/cms/static/css/style.css†L1183-L1188】
- **Template:** Applied in `cms/drawerregister_list.html` for the draggable rows.【F:app/cms/templates/cms/drawerregister_list.html†L70-L86】
- **W3.CSS alternatives:** Use a `w3-button w3-round w3-light-grey` (or `w3-col` icon button) to indicate drag affordance, keeping only the `cursor: grab` override if required for SortableJS compatibility.

### Dropdown toggle button
- **Custom selector:** `.dropdown-toggle` is currently styled via the navigation stylesheet.【F:app/cms/static/css/style.css†L134-L141】
- **Template:** The Reports menu toggle uses the class in `base_generic.html`.【F:app/cms/templates/base_generic.html†L60-L69】
- **W3.CSS alternatives:** Switch to `w3-button w3-hover-none` combined with the standard W3 dropdown markup so the icon rotation and visibility rely on `w3-show` / `w3-hide` classes rather than bespoke transforms.

### Form error styling
- **Custom selector:** `ul.errorlist.nonfield` applies bespoke red backgrounds and borders.【F:app/cms/static/css/style.css†L769-L783】
- **Templates:** Account/login flows and admin OCR prompt rely on Django’s default `errorlist` output, which picks up these styles.【F:app/cms/templates/admin/do_ocr_prompt.html†L7-L37】
- **W3.CSS alternatives:** Replace with a W3 alert panel such as `w3-panel w3-pale-red w3-leftbar w3-border-red` while keeping semantic `<ul>` markup for screen readers.

### Other active helpers
- **`.logo_image`** ensures the NMK logo scales correctly in navigation.【F:app/cms/static/css/style.css†L26-L28】 Replace with `w3-image` plus inline `style="max-width:120px"` or W3 width utilities; keep ARIA text hidden via `.sr-only`.
- **`.logout-form`** only zeros margins.【F:app/cms/static/css/style.css†L98-L100】 Swap for `class="w3-margin-0"` on the `<form>` tag to lean on W3 spacing utilities.

### Unused / legacy selectors to prune
Selectors present in `style.css` but no longer referenced in templates include `.actions`, `.card`, `.template_form_*`, `.search-bar`, `.list-page-header`, `.template_import`, `.pagination_*`, `.helptext`, `.Import_*`, `.reset_button`, `.table-container`, `.template-detail-*`, `.step-link`, `.hidden-mobile`, `.icon-text`, `.dropdown-list-select`, `.select2-*`, etc.【F:app/cms/static/css/style.css†L286-L1194】 None of these selectors surfaced in the repository scan, so they can be removed outright or rewritten with W3 equivalents during cleanup. If any functionality returns, prefer W3 utilities such as `w3-table-all`, `w3-row-padding`, `w3-hide-small`, and `w3-button` before reintroducing bespoke rules.

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
