# User Rights

This guide outlines which navigation entries are visible to each role and what create/read/update/delete (CRUD) actions are available in the public site. Superusers can always fall back to the Django admin for operations that are not surfaced in the application UI.

## Roles

- **Public user** – an unauthenticated visitor or anyone without a staff group assignment; they only see the login prompt in the sidebar.【F:app/cms/templates/base_generic.html†L63-L73】
- **Curator** – member of the Curators group, gaining access to curator dashboards and preparation workflows.【F:app/cms/views.py†L220-L233】【F:app/cms/views.py†L946-L960】
- **Collection manager** – member of the Collection Managers group, unlocking accession management, locality editing, and storage tools.【F:app/cms/views.py†L234-L267】【F:app/cms/views.py†L115-L116】
- **Preparator** – member of the Preparators group who can update the preparation records assigned to them.【F:app/cms/views.py†L980-L995】【F:app/cms/views.py†L1017-L1091】
- **Intern** – member of the Interns group with access to the scanning dashboard for drawers assigned to them.【F:app/cms/views.py†L269-L285】
- **Superuser** – Django administrators who satisfy every permission check in the navigation and view logic.【F:app/cms/templates/base_generic.html†L50-L61】【F:app/cms/views.py†L449-L457】

## Accessions

The Accessions link is always visible in the sidebar navigation.【F:app/cms/templates/base_generic.html†L45-L61】 The list and detail views filter out unpublished records for anyone who is not a curator, collection manager, or superuser, so public visitors, interns, and preparators only see published entries.【F:app/cms/views.py†L517-L534】【F:app/cms/views.py†L464-L472】 Curators may browse the full catalogue but the creation and editing endpoints are guarded by the collection-manager check, leaving them read-only on the public site.【F:app/cms/views.py†L517-L534】【F:app/cms/views.py†L793-L944】 Collection managers and superusers can create accessions, add related content, and edit existing records through those protected views.【F:app/cms/views.py†L793-L944】

## Localities

Localities are visible to every visitor via the sidebar.【F:app/cms/templates/base_generic.html†L45-L61】 The list view has no access restriction, but locality details only expose unpublished accessions to authenticated curators, collection managers, or superusers.【F:app/cms/views.py†L676-L706】 Creating a new locality requires collection-manager privileges, and only the same roles see the edit button on the detail page.【F:app/cms/views.py†L377-L414】【F:app/cms/templates/cms/locality_detail.html†L11-L49】 Everyone else—including preparators and interns—can browse locality information but cannot change it.

## Places

Places are also always visible in navigation.【F:app/cms/templates/base_generic.html†L45-L61】 Anyone can browse the list and detail pages, but only superusers and collection managers pass the `can_manage_places` check that protects the create and edit forms.【F:app/cms/views.py†L115-L116】【F:app/cms/views.py†L417-L441】 As a result, curators, preparators, interns, and the public have read-only access to places from the public site.

## References

References appear for every visitor and the list view is unrestricted.【F:app/cms/templates/base_generic.html†L45-L61】【F:app/cms/views.py†L663-L673】 The “New Reference” button and detail-page edit link show only for superusers and collection managers, reflecting that those roles manage the bibliography.【F:app/cms/templates/cms/reference_list.html†L13-L18】 Other roles can view references but cannot add or modify them through the front end.

## Field Slips

Field Slips are a specialist tool: the sidebar entry only appears for superusers and collection managers, and the list view enforces the same requirement.【F:app/cms/templates/base_generic.html†L50-L61】【F:app/cms/views.py†L449-L457】 Those roles can create and edit slips using the dedicated forms surfaced in the list and detail templates.【F:app/cms/templates/cms/fieldslip_list.html†L14-L18】【F:app/cms/views.py†L301-L320】 Curators, preparators, interns, and the public do not see the navigation item and cannot reach the list because of the access check.

## Preparations

The Preparations link is visible to superusers, collection managers, and curators; preparators and other users do not see it.【F:app/cms/templates/base_generic.html†L54-L56】 The list view applies the same restriction, so only those roles can browse all preparations or launch the “New Preparation” flow.【F:app/cms/views.py†L946-L973】 Within individual records, superusers can always edit, curators can edit or delete when they are the assigned curator, and preparators can update records assigned to them even though they must reach the page via a direct link or notification rather than navigation.【F:app/cms/views.py†L980-L1091】 Collection managers can start new preparations but must rely on the assigned curator or preparator to update or finish them.【F:app/cms/views.py†L946-L1091】

## Drawers

Drawer management is limited to superusers and collection managers: the navigation entries, list view, and all CRUD views share a mixin that checks for those roles.【F:app/cms/templates/base_generic.html†L58-L60】【F:app/cms/views.py†L1298-L1428】 Interns interact with drawers through the dashboard scanning workflow instead, where they can see drawers assigned to them and start or stop scanning sessions.【F:app/cms/views.py†L269-L285】【F:app/cms/views.py†L1431-L1437】 All other roles have no navigation access to drawer registers.

## Storages

Storage areas follow the same pattern: only superusers and collection managers see the navigation entry, pass the access mixin, and can create or edit storage records.【F:app/cms/templates/base_generic.html†L58-L61】【F:app/cms/views.py†L1298-L1375】 Other roles, including curators, preparators, interns, and the public, cannot reach the storage list through the front-end navigation.

## Summary of CRUD Rights

`C` = create, `R` = read, `U` = update, `D` = delete, `🚫` = not visible in navigation/blocked. “Published” indicates that only published records are visible to the role. Preparations have role-specific nuances noted below.

| Entity | Public | Curator | Collection Manager | Preparator | Intern | Superuser |
| --- | --- | --- | --- | --- | --- | --- |
| Accessions | R (published) | R (all) | C,R,U | R (published) | R (published) | C,R,U |
| Localities | R | R | C,R,U | R | R | C,R,U |
| Places | R | R | C,R,U | R | R | C,R,U |
| References | R | R | C,R,U | R | R | C,R,U |
| Field Slips | 🚫 | 🚫 | C,R,U | 🚫 | 🚫 | C,R,U |
| Preparations | 🚫 | C,R,U,D* | C,R* | 🚫† | 🚫 | C,R,U,D |
| Drawers | 🚫 | 🚫 | C,R,U | 🚫 | 🚫 | C,R,U |
| Storages | 🚫 | 🚫 | C,R,U | 🚫 | 🚫 | C,R,U |

*Curators can update or delete a preparation only when they are the assigned curator, and preparators can update the records assigned to them; collection managers launch new preparations but must rely on the assigned staff to revise them.【F:app/cms/views.py†L980-L1109】*

†Preparators do not see the Preparations link in navigation but can edit the records where they are set as the preparator when given a direct link.【F:app/cms/templates/base_generic.html†L54-L56】【F:app/cms/views.py†L980-L1091】
