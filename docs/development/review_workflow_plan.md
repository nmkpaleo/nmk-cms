# Review Workflow Plan

## Goals
- Ensure each specimen list page is reviewed by a single reviewer at a time.
- Record review status transitions and reviewer assignments for auditability.
- Support administrative override to release or reassign locked pages.

## Data Model Additions
- **Review status**: track the human review lifecycle (pending, in review, approved, rejected).
- **Reviewer lock**: store the assigned reviewer and lock timestamp to avoid collisions.
- **Audit trail**: retain history of reviewer assignments and status changes for accountability.

## Workflow Summary
1. When a reviewer opens a page, the system assigns the reviewer and records a lock timestamp.
2. The review status moves to “in review” while the lock is active.
3. Admins can release or reassign locks if needed.
4. Approval or rejection updates the review status and records completion timestamps.

## Operational Notes
- Locks are time-bound and can be reclaimed after expiration.
- Review status should remain independent of ingestion pipeline status for clarity.
- Changes to review status and locks must be captured in the audit history.
