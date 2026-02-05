# Approval Workflow

## Overview
Approving a specimen list page creates accession records, accession rows, and field slips from the reviewed row data. Approval also records results for auditing and moves the page image into the approved storage area.

## Approval steps
1. Reviewers validate row data and ensure accession numbers are present.
2. The system maps row data into accession, accession row, and field slip records.
3. Import results are stored with the reviewed rows and summarized on the page.
4. The page status updates to approved and the image is moved into the approved pages directory.

## Notes for administrators
- If approval fails due to missing data, errors are recorded alongside each row.
- Locks and approval timestamps are recorded for audit history.
