# Specimen list page classification

## Overview
Specimen list pages are classified before extraction to route them correctly. Pages categorized as specimen lists move into the review workflow, while non-specimen pages are routed to a text-only view. Specimen list pages are split into accession detail lists and accession/field relation lists.

## Admin queue operations
### Requeue classification
Use the Specimen List Pages admin list to select one or more pages and run the **Requeue classification** action. This resets the classification status, clears confidence/notes, and marks the page as pending so it can be reprocessed.

After you requeue, the next classification job run will pick up those pages, classify them again, and update their page type, confidence, and notes. Until the job runs, the pages remain in a pending classification state.

### Monitoring status
The list view displays classification status, confidence, page type, and pipeline status. Use the filters to focus on pending or failed pages and review confidence thresholds.

## Running classification jobs
### PythonAnywhere
1. Open the PythonAnywhere dashboard and go to the **Tasks** tab.
2. Add a scheduled task that runs the classification management command from your virtualenv:
   - Command: `~/path/to/venv/bin/python ~/path/to/project/app/manage.py classify_specimen_pages --limit 100`
3. Set the schedule to match your desired cadence (for example, every 10 minutes).
4. Save the task and monitor the task log for errors.

### Docker production
1. Ensure the application container can access the Django settings and media volume.
2. Run the command inside the running web container or a one-off task container:
   - Command: `docker compose exec web python app/manage.py classify_specimen_pages --limit 100`
3. To schedule it, add a cron entry on the host or in a worker container that invokes the same command at a fixed interval.
4. Verify logs to confirm pages are being classified and failures are reported.

## Rollback
If classification needs to be halted, disable the specimen list classification feature flag in the environment settings. This stops new classification runs without removing stored results.

## Troubleshooting
- **Missing images**: Ensure the PDF splitting step completed and page images are stored before running classification.
- **Stuck pages**: Requeue classification and confirm the batch job is running.
