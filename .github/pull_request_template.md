## Review timing

Open new pull requests as drafts. Let the required CI and CodeQL checks finish successfully, fix any failures, then mark the pull request ready and request reviewers. This applies to both main and prod.

## Summary

Describe the problem and the approach taken.

## Validation

List the checks you ran and their results.

## Risk and rollback

Describe operational, security, migration, or compatibility risks and how this
change can be reversed.

## Checklist

- [ ] The change is focused and contains no unrelated edits.
- [ ] Required CI and CodeQL checks passed before reviewers were requested.
- [ ] Tests were added or updated where feasible.
- [ ] Relevant local tests and checks pass.
- [ ] User, administrator, or developer documentation was updated if needed.
- [ ] `CHANGELOG.md` was updated for a user-visible or operational change.
- [ ] No secret or sensitive personal data is included.
- [ ] Deployment, migration, and rollback steps are documented if applicable.
