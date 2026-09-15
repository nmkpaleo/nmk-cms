# GitHub workflow and security

This guide describes the repository's intended multi-maintainer workflow. GitHub
rules and settings should enforce this policy; maintainers should periodically
compare the live settings with this document.

## Branch and pull-request workflow

1. Create a focused branch from the latest `main`.
2. Open a pull request into `main` and complete its risk, validation, and
   rollback notes.
3. Keep the branch synchronized with `main` when GitHub reports it as out of
   date.
4. Wait for `CI / test` and CodeQL to pass.
5. Obtain at least one approval from someone other than the author and resolve
   every review conversation.
6. Merge through the normal pull-request path. Do not push directly to `main`
   or use administrator bypass for routine work.

Two approvals are not normally required. CODEOWNER review applies only to the
sensitive paths listed in `.github/CODEOWNERS`.

Dependabot and other bots follow the same checks and review requirements. Bots
may create and update branches, but they do not bypass CI or approve their own
pull requests.

## Continuous integration

`.github/workflows/ci.yml` runs for pull requests into `main`, pushes to `main`,
and manual dispatches. It uses a read-only token and does not consume repository
secrets. The `test` job runs:

- Django system checks;
- migration drift detection;
- application tests with the 70% coverage floor; and
- Markdown documentation tests.

Do not add publishing, deployment, or production credentials to pull-request
CI. Keep those operations in separately permissioned jobs and trusted events.

All external actions must use immutable 40-character commit SHAs with a release
version comment. `.github/dependabot.yml` groups weekly GitHub Actions updates;
review publisher, release notes, permission changes, and CI results before
merging an update.

## Updating CI dependency locks

CI, staging, and production quality jobs install `app/requirements-ci.lock` with
`pip --require-hashes`. The optional inference job uses
`app/requirements-tooth-marking-cpu.lock`. Both locks target Linux x86_64 and
Python 3.10; keep the editable requirements files as the dependency inputs.
The container build still uses `app/requirements.txt`.

After changing an input requirement (including a Dependabot update), regenerate
and commit its lock file using uv 0.12.14:

```sh
uv pip compile app/requirements-ci.in --python-version 3.10 --python-platform x86_64-unknown-linux-gnu --generate-hashes --output-file app/requirements-ci.lock --no-emit-index-url
uv pip compile app/requirements-tooth-marking-cpu.txt --python-version 3.10 --python-platform x86_64-unknown-linux-gnu --generate-hashes --output-file app/requirements-tooth-marking-cpu.lock --emit-index-url --index-strategy unsafe-best-match
```

The second command uses pip-compatible index selection because the input combines
PyPI with the official PyTorch CPU index. Review package versions, origins, and
hash changes before merging. Existing lock versions are preserved when compatible;
use `--upgrade-package NAME` for an intentional dependency upgrade.

Validate with a clean Linux Python 3.10 environment:

```sh
python -m pip install --require-hashes -r app/requirements-ci.lock
python -m pip check
python -m pytest tests/test_dependency_locks.py tests/docs
```

Run the usual application CI checks and the optional inference workflow when its
lock changes. The inference check imports both libraries and exercises the compiled
CPU non-maximum suppression operation to detect incompatible paired wheels.
Rollback by reverting the workflow and lock-file changes together.

## Security monitoring

- CodeQL default setup scans Python, JavaScript/TypeScript, and Actions changes.
- Dependabot alerts and security updates monitor supported dependency manifests.
- Secret scanning and push protection detect supported credential patterns.

An alert is not resolved merely because a pull request exists. Confirm the fix
is present on `main` and let GitHub close the alert, or record evidence and a
rationale before dismissal. Never expose alert details or credential values in
public issues, logs, or pull requests.

Follow [SECURITY.md](../../SECURITY.md) for private vulnerability reports.

## Emergency bypass

Emergency bypass is for an actively exploited vulnerability or an outage where
the normal review delay creates greater harm. Use only the designated emergency
team or account, never a general administrator override.

After any bypass:

1. Record the actor, reason, affected commit, and time.
2. Run all skipped checks as soon as service is stable.
3. Obtain retrospective independent review.
4. Revert or follow up through a normal pull request if validation fails.
5. Review whether the bypass scope should be reduced.

## Settings review

Repository administrators should periodically confirm that branch and tag
rules, Actions permissions, required checks, CODEOWNERS, environments, and
Dependabot remain consistent with this guide. Organization-level bypass and
Actions policies require an organization owner to verify them.
