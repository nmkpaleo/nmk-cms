# OpenAI usage and credit reporting

The **ChatGPT usage** link in admin opens `/admin/chatgpt-usage/`.

- Token charts, model filters, scan counts and processing times use stored OCR records.
- The main monetary total comes from OpenAI's Costs API, scoped to the configured project.
- Historical per-scan costs remain labelled **Local estimate**. They use configured prices and may be incomplete or outdated.
- Current account credit and forecasts include **all organization spending**, including other projects and unassigned charges. They do not change with report filters.
- Monthly budget progress uses the current UTC calendar month and project spending, independently of the selected report dates. A budget is not prepaid credit.

## Enable cost synchronization

Apply migrations with `python app/manage.py migrate`. Configure these environment variables (or the existing `config.json` / local settings mechanism):

| Setting | Purpose / default |
| --- | --- |
| `OPENAI_ADMIN_KEY` | An OpenAI admin API key with permission to read organization costs; keep it server-side |
| `OPENAI_ORG_ID` | Organization whose billing is being monitored |
| `OPENAI_PROJECT_ID` | This application's project; required for project totals and budget progress |
| `LLM_USAGE_MONTHLY_BUDGET_USD` | Project planning budget; default `120` |
| `LLM_BILLING_STALE_HOURS` | Suppress forecasts after this many hours without fresh costs; default `24` |
| `LLM_BALANCE_STALE_DAYS` | Require another balance verification after this many days; default `30` |
| `LLM_CREDIT_WARNING_DAYS` | Low-credit warning threshold; default `14` |
| `LLM_CREDIT_URGENT_DAYS` | Urgent threshold; default `7` |
| `LLM_PURCHASE_LEAD_DAYS` | Purchasing lead time subtracted from depletion estimate; default `7` |

Use positive freshness limits, nonnegative lead time, and warning days greater than or equal to urgent days.
The normal OCR API key is unchanged. Billing credentials are never sent to the browser.

## Synchronize from the report

On `/admin/chatgpt-usage/`, click **Synchronize OpenAI costs**. The page returns with a success or error message and retains your date/model filters. The button disables while the request is running. Opening or refreshing the report alone does not contact OpenAI.

Superusers can use the button automatically. To delegate it, grant an active staff user the Django permission with codename `cms.change_openaibillingsync` (**Can change open ai billing sync**). Viewing the report or adding credit entries alone does not grant sync access.

The button uses the same configured credentials and cost-sync logic as the scheduled command. Missing configuration is reported on the page; no credentials are entered in the browser. UI syncs have a cooperative 45-second deadline, checked between provider requests and database operations, including immediately before committing the snapshot. Active database operations may finish after the deadline; the replacement then rolls back. Where supported by the database, UI syncs fail immediately if another sync holds the billing row lock. If a slow provider or a large historical backfill exceeds it, the previous snapshot is retained; retry or use the command below. The command has no overall UI time budget, but retains per-request timeouts.

## Schedule automatic synchronization

From the repository root, run:

```sh
python app/manage.py sync_openai_costs
```

Schedule that command **hourly** with the deployment's task scheduler or host cron, as with [specimen list classification](specimen_list_classification.md).
For Docker, run `docker compose exec -T web python manage.py sync_openai_costs` from the Compose directory (the web container's working directory is `/src/app`). Use the appropriate production Compose file when applicable. Schedule a single job per organization.
The report only reads the saved snapshot; loading it does not contact OpenAI.

The first sync retrieves 35 days. To extend historical coverage:

```sh
python app/manage.py sync_openai_costs --since 2026-01-01
```

Each run refreshes the entire imported interval, follows pagination, and replaces the snapshot atomically. Re-running does not double-count costs. This also picks up delayed charges and provider corrections. A failed or invalid response preserves the previous successful snapshot and marks the report as failed. Monitor the command's exit status. Costs use UTC dates; today's amounts may be partial and recent charges may not yet appear.

## Record credit and top-ups

1. In OpenAI billing, check the organization's actual prepaid balance.
2. In the report, select **Record balance or top-up**. This requires the Django **Can add OpenAI credit entry** permission (superusers already have it).
3. Choose **Verified balance**, enter the dollar balance, the time you checked it, and a note. Verify the organization ID.
4. Click **Synchronize OpenAI costs**, run the command, or wait for the scheduled run. The sync separately requests organization spending from that verification timestamp, with second precision; it does not prorate a day's spending.
5. After buying credits, add a **Top-up / adjustment** with a positive amount and the time it took effect. Use a negative adjustment for expired credits or other reductions. Only adjustments after the latest verified balance and before the sync cutoff are included.

A verified balance already includes earlier top-ups: do not enter them again with later timestamps. Entries are append-only in admin. Correct a mistaken adjustment with an opposite adjustment, or record a new verified balance. An incorrect verified balance should be replaced with a new check. Django's admin log records who added each entry.

The calculation is:

```text
Estimated credit = latest verified balance + subsequent adjustments
                   - OpenAI-reported organization costs since verification
```

There is no credit-balance API integration: top-ups, expirations and billing corrections must be recorded or reconciled by checking the balance again. The report links directly to OpenAI billing. Provider reporting delays and unrecorded changes can affect the estimate.

## Understand forecasts and alerts

The report calculates average organization spend over 7 and 30 complete UTC days, including zero-spend days. It uses the higher available rate for a conservative forecast, requiring at least seven days of imported coverage. The forecast accounts for elapsed time since the snapshot. Suggested top-up date subtracts purchasing lead time and is never earlier than today.

Warnings appear on the report at the configured thresholds. This implementation does not send email. Configure OpenAI's own spending alerts separately for notifications outside this page.

Missing coverage, a new unsynchronized balance, stale costs, an old balance verification or a failed sync suppresses the forecast. No recent spending produces **Unavailable**, not unlimited credit. A fresh estimate at or below zero is urgent. Very distant forecasts (10+ years) omit the top-up date.

The report does not claim an exact remaining token count. Token prices vary by model and token type. The API's remaining-token rate-limit headers measure temporary capacity, not purchased credit. Estimated scans remaining are also omitted because OCR records do not contain every billable request.

## Token coverage and filtering

The existing OCR usage storage retains one record per media item. Reprocessing replaces that record; classification, retries and other requests may be missing. The existing token charts remain useful for recorded scans, but are not the financial ledger. OpenAI-reported costs cover the configured project's billable activity.

Model filters apply to local token records and their historical estimates. Clear the model filter to see provider-reported project costs; those imported costs are not attributed to individual models. Dates outside imported billing coverage show **Unavailable**, not zero. Account status and current-month budget are unaffected by these filters.

## Rollback

Disable the scheduled cost sync and redeploy the previous application version.
The new tables are additive and can remain in place without affecting the old report.
Retain credit entries for auditing; reversing migration 0091 removes the billing and credit history, so export that data before any schema rollback.

## References

- [OpenAI Costs API](https://developers.openai.com/api/reference/python/resources/admin/subresources/organization/subresources/usage/methods/costs)
- [OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits)
- [OpenAI spending alerts](https://developers.openai.com/api/docs/guides/spend-limits)
- [Admin guides](README.md)
