# Release checklist (`main` -> `prod`)

This project ships production releases by merging a pull request from `main` into `prod`.

## Versioning model

- Use Semantic Versioning tags: `vMAJOR.MINOR.PATCH` (for example `v1.4.2`).
- The workflow `.github/workflows/release-on-prod-merge.yml` creates the next tag automatically after a PR is merged into `prod`.
- Bump level comes from PR labels:
  - `release:major` -> major bump
  - `release:minor` -> minor bump
  - no release label -> patch bump

## Pre-merge checklist

1. Create PR from `main` to `prod`.
2. Confirm CI is green.
3. Add one release label (`release:major` or `release:minor`) when needed.
4. Review changelog impact and migrations.
5. Merge PR into `prod`.

## What happens after merge

1. `release-on-prod-merge` computes the next `v*` tag.
2. The workflow pushes the tag and creates a GitHub Release with generated notes.
3. `production-ci` runs on `prod` and on `v*` tags.
4. Docker image build gets `APP_VERSION` from the git reference (`v*` tag on release builds).

## Showing version in the UI

The UI footer renders `Version: <value>` from `APP_VERSION`.

Resolution order in code:

1. `APP_VERSION` environment variable.
2. `git describe --tags --always --dirty`.
3. short git SHA.
4. `dev` fallback.

### How to verify locally

```bash
cd app
APP_VERSION=v1.2.3 python manage.py runserver
```

Open the app and confirm footer shows `Version: v1.2.3`.
