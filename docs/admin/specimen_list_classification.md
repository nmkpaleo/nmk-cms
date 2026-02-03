# Specimen list page classification

## Overview
Specimen list pages are classified before extraction to route them correctly. Pages categorized as specimen lists move into the review workflow, while non-specimen pages are routed to a text-only view.

## Admin queue operations
### Requeue classification
Use the Specimen List Pages admin list to select one or more pages and run the **Requeue classification** action. This resets the classification status, clears confidence/notes, and marks the page as pending so it can be reprocessed.

### Monitoring status
The list view displays classification status, confidence, page type, and pipeline status. Use the filters to focus on pending or failed pages and review confidence thresholds.

## Rollback
If classification needs to be halted, disable the specimen list classification feature flag in the environment settings. This stops new classification runs without removing stored results.

## Troubleshooting
- **Missing images**: Ensure the PDF splitting step completed and page images are stored before running classification.
- **Stuck pages**: Requeue classification and confirm the batch job is running.
