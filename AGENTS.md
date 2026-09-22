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
- Keep docs lightweight: headings, examples, and short “How to” sections.
- If a docs verification step tries MkDocs, skip it and explain why in the PR.
