# Review workflow (user)

This page describes the specimen list review workflow from a reviewer perspective.

## Access
- Open **Specimen list review queue** from the CMS navigation.
- Queue access can be turned on/off with `FEATURE_REVIEW_UI_ENABLED`.

## Queue behavior
- The queue currently lists pages of type **Specimen list (accession details)**.
- Use filters for source, pipeline status, reviewer, and confidence.
- Approved pages show a **View** action instead of **Review**.

## Review page modes
- **Review mode**: editable extracted rows with save/reject/approve actions.
- **View mode** (`?mode=view`): read-only extracted rows.
- The **Back to queue** button is always available in the page header.

## Approve behavior (high-level)
When a page is approved, reviewed row data is transformed into CMS records.
Taxon values are normalized and qualifiers (for example `cf.` and `aff.`) are captured so downstream records remain consistent.

## Rollout note
If review UI rollout must be paused, set `FEATURE_REVIEW_UI_ENABLED=0` and restart the app.
