# Accession number series analysis

## Current model shape
- `cms.models.AccessionNumberSeries` stores the owner `user`, `start_from`, `end_at`, `current_number`, and `is_active`. Validation currently splits series pools by username: a dedicated `tbi` user is treated separately from all other users. Overlap checks are scoped to the `tbi` pool vs the non-`tbi` pool. Only one active series is allowed per user. `get_next_batch` increments `current_number` while enforcing the range limits. The model orders by `user` then `start_from` and is tracked via `HistoricalRecords`.
- Related accession numbering is used in tests and views that expect series lookup by `user`. There is no existing organisation linkage or FK on the series model or user model.

## Admin/UI touch points
- `AccessionNumberSeriesAdmin` (`cms.admin`) uses `AccessionNumberSeriesAdminForm`, exposes `user`, `start_from`, `end_at`, `current_number`, and `is_active`, and includes widget metadata for mapping the `tbi`- vs shared-series pools.
- `AccessionNumberSeriesAdminForm` (`cms.forms`) builds pool metadata and initial values based on whether the selected/acting user is the `tbi` username. On creation, `start_from`/`current_number` are auto-derived from the next number in the applicable pool, with one active series enforced per user.

## Derivation utilities
- `AccessionNumberSeriesAdminForm` derives next start numbers via `_next_start_for_pool`, which selects the highest `end_at` within the `tbi` pool or the shared pool (all other users), and sets a base of `1_000_000` for `tbi` vs `1` for others. Metadata includes a `data-dedicated-user-id` pointing to the `tbi` user when present, and a JSON map of pool starts used by admin JS.

## Observations for organisation linkage
- All series logic is keyed solely on `user.username` comparisons (specifically `"tbi"`). No abstraction exists for organisations or groupings. Introducing organisation support will require:
  - Adding an organisation model/FK and updating overlap/uniqueness checks to operate on organisation + user scope instead of the username pool split.
  - Updating the admin form metadata and start-number derivation utilities to respect organisation context rather than username-specific branching.
  - Ensuring downstream usages that query by `user` are audited and migrated to organisation-aware lookups to prevent cross-organisation leakage.
