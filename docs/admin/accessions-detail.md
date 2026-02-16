# Accession detail review

Collection managers and superusers can use the accession detail page to audit data quality before publishing records.

## What changed

- The upper half of the page now splits into two columns on desktops: the **Accession overview** card remains on the left, while the **Specimen details**, **Related field slips**, and **Horizon** tables stack on the right.
- References, Media, and Comments stay in the lower half of the page. Their order has not changed, so any saved bookmarks or screenshots still match the original flow.
- Hovering or focusing a media thumbnail opens a centred preview panel on large screens. This does not alter the existing “open in new tab” behaviour when you click the thumbnail.
- The **Create and link new field slip** modal now closes any open Select2 dropdowns and hides the background form controls while the dialog is active to avoid overlapping UI.

## Admin checklist

1. Confirm that restricted controls (Add specimen, Link field slip, Add reference, Add comment) continue to respect group membership.
2. When reviewing large images, use the hover preview to verify labels without leaving the page. Press <kbd>Escape</kbd> or move focus away to hide the preview.
3. Continue to use the existing buttons to edit the accession, manage field slips, or upload media; the modal workflow and permissions are unchanged, but the overlay now masks the background select widget and closes open dropdowns automatically.
4. In the accession row detail view, confirm that the Elements table shows a delete action only for authorized managers, and that deletion requires a confirmation step before removing a record.
