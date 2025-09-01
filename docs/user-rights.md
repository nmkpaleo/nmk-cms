# User Rights

This guide outlines visibility and operations available to different user roles.

## Roles
- **Public User** – not authenticated.
- **Curator** – member of the "Curators" group.
- **Collection Manager** – member of the "Collection Managers" group.
- **Superuser** – Django administrator with all permissions.

## Accession
- **Public User**: can view only published accessions on list pages and locality details. Attempting to access an unpublished accession detail returns a 404 page. No editing actions are available.
- **Curator**: can view all accessions, including unpublished ones, but cannot create or edit them.
- **Collection Manager / Superuser**: full access to all accessions. They may view unpublished records, edit accession information, and manage related data such as geology, specimens, references, comments, and media.

## Locality
- **Public User**: can view locality pages. Only published accessions are listed for each locality. Editing is not allowed.
- **Curator**: can view all accessions associated with a locality, regardless of publication state.
- **Collection Manager / Superuser**: can edit localities and see all associated accessions, including who accessioned them.

