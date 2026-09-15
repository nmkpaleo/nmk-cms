# TASK-001 Analysis: Approve-page execution path and media-location drift points

## Task object

```json
{
  "id": "TASK-001",
  "title": "Trace approve-page execution path and identify media-path drift points",
  "description": "Document current control flow from /specimen-lists/pages/<id>/review/ approve action to file move and Media persistence points.",
  "type": "analysis",
  "paths": ["apps/", "templates/"],
  "dependencies": [],
  "acceptance_criteria": [
    "Current move mechanism and DB update sequence are clearly mapped.",
    "Failure points causing file/DB mismatch are identified."
  ],
  "testing": [
    "n/a (analysis task)"
  ]
}
```

## Entry point and route

- URL: `/specimen-lists/pages/<id>/review/`
- Route name: `specimen_list_page_review`
- View: `SpecimenListPageReviewView`
- Action trigger: POST form button `action=approve` in the review template.

## Observed approve flow (current implementation)

1. User clicks **Approve page** in the page review form.
2. `SpecimenListPageReviewView.post()` receives `action=approve`.
3. View validates/saves row formset (if valid) and calls `_update_review_status(..., action="approve")`.
4. `_update_review_status()` opens a transaction and calls `approve_page(page=page, reviewer=request.user)`.
5. `approve_page()` opens its own `transaction.atomic()` block, reloads page with `select_for_update()`, then:
   - approves each row via `approve_row()`,
   - raises `ValidationError` if any row has approval errors,
   - calls `_ensure_media_for_page(...)` for each accession/accession-row pair,
   - saves page status fields (`pipeline_status`, `review_status`, `reviewed_at`, `approved_at`, lock/reviewer).
6. After the transaction commits, `approve_page()` runs:
   - `_store_page_results(page, results, reviewer)`
   - `_move_page_image(page, reviewer)`
7. `_move_page_image()` copies the page image from `/pages/` to `/pages/approved/`, deletes old file if renamed, updates `SpecimenListPage.image_file`, and saves that field.

## Where Media is created and what location is persisted

`_ensure_media_for_page(...)` creates `Media` records during the transaction before `_move_page_image()` runs.

Current creation behavior:
- duplicate check keys on `accession`, `accession_row`, and `media_location=page.image_file.name`
- new `Media` record is created with:
  - `file_name` from `os.path.basename(page.image_file.name)`
  - `format` from current extension
  - `media_location=page.image_file` (the pre-move path)

Result: created `Media.media_location` points at the original `/pages/...` path at creation time.

## Confirmed drift point

- The page file is moved **after** approval transaction completion.
- Only `SpecimenListPage.image_file` is updated in `_move_page_image()`.
- Existing `Media` rows created in the same approve flow are **not** updated to the new `/pages/approved/...` location.

This yields file/DB drift:
- storage file ends up at `/pages/approved/...`
- `Media.media_location` may remain `/pages/...`

## Additional mismatch and consistency risks

1. **Non-atomic post-commit move**
   - `_move_page_image()` runs outside the main approval transaction.
   - Approval status/data can commit successfully even if file move/save fails afterward.

2. **Partial update scope**
   - `_move_page_image()` updates only `SpecimenListPage.image_file`.
   - No synchronized update for related `Media` records tied to the same page image.

3. **Duplicate detection tied to pre-move path**
   - `_ensure_media_for_page()` duplicate check includes exact `media_location` string.
   - Once path changes to `/pages/approved/...`, the old-path duplicate key no longer matches canonical final location semantics.

4. **Storage operation ordering edge case**
   - New file save occurs before old file delete.
   - If delete fails, system can leave both old and new files while DB points only to the newly assigned page path.

5. **Idempotency gap across retries**
   - If an approval operation is retried around failures, path-based duplicate checks can permit inconsistent media records (old-path vs new-path variants) depending on failure timing.

## Concrete handoff for TASK-002

The next task should centralize move+sync so one service owns:
- final destination path computation,
- file move/copy/delete behavior,
- synchronized `SpecimenListPage.image_file` and related `Media.media_location` updates,
- idempotent duplicate-safe behavior for retries,
- failure strategy that prevents durable page/media path divergence.

## Acceptance criteria coverage

- **Current move mechanism and DB update sequence are clearly mapped**: covered in "Observed approve flow" and "Where Media is created and what location is persisted".
- **Failure points causing file/DB mismatch are identified**: covered in "Confirmed drift point" and "Additional mismatch and consistency risks".
