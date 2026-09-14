# Contributing

Thank you for improving NMK CMS.

## Before you start

- Read the [development guide](docs/development/README.md) and
  [environment setup](docs/development/environment-setup.md).
- Follow the [GitHub workflow and security guide](docs/development/github-workflow.md)
  for CI, review, bot, and emergency-bypass policy.
- Open an issue for substantial behavior or data-model changes before investing
  in a large implementation.
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Make a change

1. Create a focused branch from the latest `main`.
2. Keep the change narrow and preserve unrelated work.
3. Add or update tests for behavior changes.
4. Update `CHANGELOG.md` when the change affects users or operations.
5. Update relevant Markdown documentation under `docs/`.

Documentation is plain Markdown. Do not add MkDocs configuration or run an
MkDocs build.

## Validate locally

The pull-request workflow runs these checks with Python 3.10 and SQLite:

```bash
cd app
python manage.py check
python manage.py makemigrations --check --dry-run
cd ..
python -m pytest app/cms/tests tests --ignore=tests/docs --cov=app --cov-fail-under=70
python -m pytest tests/docs
```

See [testing guidance](docs/development/testing.md) for additional options.

## Open a pull request

- Explain the problem, approach, risk, and rollback path.
- Link related issues and identify migrations or deployment steps.
- Wait for CI and CodeQL to pass.
- Obtain an independent maintainer approval and resolve every review thread.
- Do not use administrator bypass for routine changes.

Dependabot and other bot pull requests follow the same CI and review rules as
human-authored changes.
