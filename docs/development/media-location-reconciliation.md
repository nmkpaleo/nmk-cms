# Media location reconciliation

Use this command to reconcile legacy `Media.media_location` rows that still point to a pre-approval page path while an approved-page file already exists.

## Rollout guidance

1. Start with a dry run in staging.
2. Compare dry-run output with a sample of approved specimen pages.
3. Run the command in small batches using `--limit`.
4. Verify media location updates and history attribution after each batch.
5. Repeat in production during a low-traffic window.

## Dry run

```bash
python app/manage.py reconcile_media_locations --dry-run
```

This reports how many rows would be updated without writing database changes.

## Apply changes

```bash
python app/manage.py reconcile_media_locations --actor-username <username>
```

`--actor-username` is required for persisted updates so model save hooks and history attribution have a valid current user context.

## Optional limit

```bash
python app/manage.py reconcile_media_locations --dry-run --limit 100
```

Use this for staged rollouts on large datasets.

## Rollback guidance

- If a batch introduces unexpected changes, stop further runs immediately.
- Restore affected records from database backup or history snapshots based on the change window.
- Re-run in dry-run mode after correction to confirm expected targets before applying again.

## Known limitations

- The command only updates rows where an approved target file already exists.
- Rows without a matching approved file are reported as skipped and require manual investigation.
