# Agent instructions

## Branch workflow
- Never write or modify code directly on `main`.
- Before starting new code changes, create and switch to a new, focused branch from the latest `main`.
- Continue work for the same task on its existing feature branch; create a new branch for each new task.
- Commit and push changes on the feature branch, then open a pull request into `main`. Never commit or push directly to `main`.

## Documentation
- Documentation lives in /docs as plain Markdown (no MkDocs, no mkdocs.yml).
- Do NOT run `mkdocs build` or add MkDocs config.
- Write docs as Markdown files in /docs with relative links.
- Keep docs lightweight: headings, examples, and short "How to" sections.
- If a docs verification step tries MkDocs, skip it and explain why in the PR.
## Commit and pull request execution
- On the feature branch, run git diff --check and the relevant tests before staging.
- Stage only task files with git add -- <paths> and create one focused commit using git commit -m <message>.
- Push with git push -u origin <feature-branch>.
- Open the PR with gh pr create --base main --head <feature-branch>, including a concise summary and verification notes.
- If Git cannot create .git/index.lock, check for an existing lock/process first; do not delete an active lock. Retry after resolving the filesystem permission issue.
