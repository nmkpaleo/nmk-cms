# Navigation overview

The NMK CMS now uses a unified W3.CSS navigation bar across every page that extends `base_generic.html`. The header keeps actions on a single horizontal line so the primary links, the Reports dropdown, and the authentication controls remain visible together on large screens while collapsing into a touch-friendly menu on small devices.

## Primary links

The following links are always available when you have permission to view them:

- **Accessions**, **Localities**, **Places**, and **References** are presented as `w3-bar` buttons with consistent hover states.
- Additional links (Field Slips, Preparations, Drawers, Storages, QC History) appear automatically when your user account matches the required group or staff role.

Keyboard users can Tab through the links in order. The navigation has `aria-label="Primary navigation"` so screen readers announce it as the main site menu.

## Reports dropdown

The Reports entry is an accessible dropdown button. Activating it by mouse, keyboard <kbd>Enter</kbd> / <kbd>Space</kbd>, or touch reveals the menu items:

- **Media Reports**
- **Accession Reports**

The dropdown traps focus while open, supports the <kbd>Arrow&nbsp;Down</kbd> key for quick access to the first item, and closes when you press <kbd>Escape</kbd> or click outside the menu.

## Authentication controls

Login and Logout actions appear in the same navigation bar:

- Anonymous visitors see a **Login** button that preserves the current path in the `next` query string so they return to the page after authenticating.
- Authenticated users see their username label followed by a **Logout** button that submits the allauth logout form with CSRF protection.

On small screens use the hamburger toggle (the icon with three lines) to expand the menu. The toggle updates `aria-expanded` as it opens and closes so assistive technologies reflect the current state.
