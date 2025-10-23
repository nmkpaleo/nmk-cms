# CMS Dashboard Overview

The dashboard adapts to the signed-in staff member and now uses W3.CSS cards with role-specific icons. Use this guide to orient new curators, collection managers, preparators, and interns.

## Global layout

- The landing page begins with a “Workspace overview” heading and card-based sections. Each card groups related tables or lists and includes contextual actions.
- Font Awesome icons appear in every heading to reinforce the type of work (vials for preparators, warehouse for collection managers, magnifying glass for QC, etc.).
- Tables inherit W3 responsive wrappers so they remain scrollable on tablets and small laptops.

## Role cards

### Preparators
- “My active preparations” lists assigned records with quick “View” buttons.
- “Priority tasks” highlights preparations started seven or more days ago.
- A green “Create preparation record” button links directly to the creation form.

### Curators
- “Completed preparations awaiting review” surfaces items assigned to the curator with direct review links.
- The same creation shortcut is available for ad-hoc preparation entries.

### Collection managers
- The card shows the accession creation shortcuts at the top. If the user lacks an active series, an informative message replaces the buttons.
- The grid below contains three columns: unassigned accessions, the user’s latest accessions (with last activity timestamps), and the embedded quality-control queue partial.

### Interns
- Interns always receive the drawer register card. The “Start” and “Stop” buttons use play/stop icons and update the running timer via JavaScript.
- If the intern is not also a collection manager, the QC queues render in a dedicated card above the drawers.

### QC experts
- Experts who do not belong to other dashboard groups see a standalone “Quality control queues” card that embeds the same partial.

## Tips for administrators

- To preview another role’s dashboard, add or remove the relevant groups (`Preparators`, `Curators`, `Collection Managers`, `Interns`) from your superuser account and refresh.
- The QC partial continues to rely on the `qc_sections` and `qc_extra_links` context prepared by `cms.views.dashboard`; avoid editing the partial in place without coordinating with the view logic.
- The JavaScript timer only initialises when the intern card is present; check the `<script>` block at the bottom of the template if you extend timer behaviour.
