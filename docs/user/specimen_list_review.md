# Specimen List Review Queue

## Overview
Use the specimen list review queue to claim pages from uploaded PDFs, review the page image, and mark the page as approved or rejected. The queue helps prevent review collisions by locking pages to a reviewer for a limited time.

## How to review pages
1. Open the review queue and filter by status, source label, or assigned reviewer.
2. Select **Review** for a page to claim the lock.
3. Review the page image and choose **Approve** or **Reject**.
4. If you need to stop reviewing, select **Release lock** so another reviewer can take over.

## Lock behavior
- Locks prevent multiple reviewers from editing the same page at the same time.
- If a lock expires, another reviewer can reload the page and take ownership.
- Releasing the lock returns the page to the pending queue.

## Approval sync behavior
- When you select **Approve page**, the system synchronizes the approved page image location and related media file locations automatically.
- The review page shows an **Approval feedback** panel that explains what to expect when synchronization succeeds or fails.
- If synchronization fails, approval is safely interrupted and an error message is displayed so you can retry.

## Operator checks after approval
1. Reopen the approved page from the queue and confirm the review completed successfully.
2. Open related media detail pages and confirm the file location reflects the approved page path.
3. If a mismatch is reported by operations, ask an administrator to run the reconciliation runbook in the development guide.

## Known limitation
- Legacy records created before this synchronization behavior may still contain pre-approval file paths until reconciliation is run.
