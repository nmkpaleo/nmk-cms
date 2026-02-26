# Coverage Ratchet Policy

## Goal
Increase automated test coverage gradually without blocking delivery with unrealistic jumps.

## Current baseline
- CI coverage floor: **70%** (`COVERAGE_FAIL_UNDER=70`).
- Ratchet step: **+2%** per sprint/release (`COVERAGE_RATCHET_STEP=2`).

These values are defined in both workflow files:
- `/.github/workflows/staging-ci.yml`
- `/.github/workflows/production-ci.yml`

## Module-level reporting
CI now prints per-module coverage in the test step with:

```bash
python -m pytest --cov=app --cov-report=term-missing:skip-covered --cov-report=xml --cov-fail-under=${COVERAGE_FAIL_UNDER}
```

`term-missing:skip-covered` shows module/file coverage and missing lines directly in CI logs.

## Ratchet process (every sprint/release)
1. Increase `COVERAGE_FAIL_UNDER` by **2** in both workflow files.
2. Merge only when the suite meets the new threshold.
3. If the threshold cannot be met for a release, keep the same floor for one cycle and document why in the PR.

## Example progression
- Sprint N: 70%
- Sprint N+1: 72%
- Sprint N+2: 74%

Repeat until the long-term target is reached.
