# User Rights

This guide outlines which navigation entries are visible to each role and what create/read/update/delete (CRUD) actions are available in the public site. Superusers can always fall back to the Django admin for operations that are not surfaced in the application UI.

## Roles

- **Public user** – an unauthenticated visitor or anyone without a staff group assignment; they only see the login prompt in the sidebar.
- **Curator** – member of the Curators group, gaining access to curator dashboards and preparation workflows.
- **Collection manager** – member of the Collection Managers group, unlocking accession management, locality editing, and storage tools.
- **Preparator** – member of the Preparators group who can update the preparation records assigned to them.
- **Intern** – member of the Interns group with access to the scanning dashboard for drawers assigned to them.
- **Superuser** – Django administrators who satisfy every permission check in the navigation and view logic.

## Accessions

The Accessions link is always visible in the sidebar navigation. The list and detail views filter out unpublished records for anyone who is not a curator, collection manager, or superuser, so public visitors, interns, and preparators only see published entries. Curators may browse the full catalogue but the creation and editing endpoints are guarded by the collection-manager check, leaving them read-only on the public site. Collection managers and superusers can create accessions, add related content, and edit existing records through those protected views.

## Localities

Localities are visible to every visitor via the sidebar. The list view has no access restriction, but locality details only expose unpublished accessions to authenticated curators, collection managers, or superusers. Creating a new locality requires collection-manager privileges, and only the same roles see the edit button on the detail page. Everyone else—including preparators and interns—can browse locality information but cannot change it.

## Places

Places are also always visible in navigation. Anyone can browse the list and detail pages, but only superusers and collection managers pass the `can_manage_places` check that protects the create and edit forms. As a result, curators, preparators, interns, and the public have read-only access to places from the public site.

## References

References appear for every visitor and the list view is unrestricted. The “New Reference” button and detail-page edit link show only for superusers and collection managers, reflecting that those roles manage the bibliography. Other roles can view references but cannot add or modify them through the front end.

## Field Slips

Field Slips are a specialist tool: the sidebar entry only appears for superusers and collection managers, and the list view enforces the same requirement. Those roles can create and edit slips using the dedicated forms surfaced in the list and detail templates. When viewing an individual slip they also see a "Related accessions" table that reuses the basic accession list, including unpublished entries so collection managers and superusers can jump straight into follow-up work. Curators, preparators, interns, and the public do not see the navigation item and cannot reach the list because of the access check.

## Preparations

The Preparations link is visible to superusers, collection managers, and curators; preparators and other users do not see it. The list view applies the same restriction, so only those roles can browse all preparations or launch the “New Preparation” flow. Within individual records, superusers can always edit, curators can edit or delete when they are the assigned curator, and preparators can update records assigned to them even though they must reach the page via a direct link or notification rather than navigation. Collection managers can start new preparations but must rely on the assigned curator or preparator to update or finish them.

## Drawers

Drawer management is limited to superusers and collection managers: the navigation entries, list view, and all CRUD views share a mixin that checks for those roles. Interns interact with drawers through the dashboard scanning workflow instead, where they can see drawers assigned to them and start or stop scanning sessions. All other roles have no navigation access to drawer registers.

## Storages

Storage areas follow the same pattern: only superusers and collection managers see the navigation entry, pass the access mixin, and can create or edit storage records. Other roles, including curators, preparators, interns, and the public, cannot reach the storage list through the front-end navigation.

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

*Curators can update or delete a preparation only when they are the assigned curator, and preparators can update the records assigned to them; collection managers launch new preparations but must rely on the assigned staff to revise them.*

†Preparators do not see the Preparations link in navigation but can edit the records where they are set as the preparator when given a direct link.
