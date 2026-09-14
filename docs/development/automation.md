# Prompt Automation Reference

For repository CI, dependency automation, action pinning, and security checks,
see [GitHub workflow and security](./github-workflow.md).

## Overview
The planning (`codex_prompt.md`) and coding (`coding prompt template.md`) guides in `docs/development/` display a dependency
snapshot so contributors understand the active Django stack. The snapshot is generated automatically from `app/requirements.txt`
by `docs/scripts/update_prompts.py`.

## Usage
1. Modify `app/requirements.txt` as part of your change.
2. Run the updater to refresh both prompt files:
   ```bash
   python docs/scripts/update_prompts.py
   ```
3. Review the resulting diffs in:
   - `docs/development/codex_prompt.md`
   - `docs/development/coding prompt template.md`
4. Commit the script, prompt docs, and requirement changes together.

## Continuous Assurance
- The script deduplicates requirement entries (first declaration wins) and groups them into curated categories. Any dependency
  that is not mapped falls back to **Additional Dependencies**.
- Unit tests in `tests/docs/test_update_prompts.py` verify the parsing and injection logic. They run with the rest of the pytest
  suite and guard against manual edits within the managed block (`<!-- DEPENDENCY_SNAPSHOT:START -->` ... `END`).
- If the script raises a marker error, ensure both prompt files still contain the start and end comments on their own lines.

### Documentation coverage
- Feature docs such as FieldSlip merge guidance live alongside the automation content. Add a short changelog entry whenever you
  document a new workflow and ensure the Markdown renders cleanly (headings, lists, and code fences) so CI docs checks continue
  to pass.

## Maintenance
- Update `CATEGORY_RULES` in `docs/scripts/update_prompts.py` when introducing new dependency groups so related packages are
  grouped meaningfully.
- When reorganising prompt content, preserve the dependency markers so the automation can continue to refresh the section.

## GitHub automation maintenance

- Pull requests into `main` run the secret-free `CI / test` check defined in
  `.github/workflows/ci.yml`.
- CodeQL default setup supplies the code-scanning checks; its configuration is a
  GitHub setting rather than a repository workflow file.
- Production and staging workflows run only for their named branches or release
  tags. They may use publishing credentials and must not be copied into an
  untrusted pull-request trigger.
- Docker publishing jobs use the staging and production GitHub environments.
  Staging accepts only the staging branch. Production accepts only prod and
  v* release tags, requires approval from a designated maintainer, prevents
  self-approval, and does not allow administrator bypass.
- Docker Hub credentials currently remain repository secrets. Rotate them into
  matching environment secrets before removing the repository-level copies;
  GitHub does not expose existing secret values for an in-place move.
- External actions are pinned to full commit SHAs. Dependabot proposes grouped
  weekly updates while preserving SHA pins and version comments.
- Review automated updates like any other change: inspect the publisher and
  release notes, keep permissions least-privilege, and require green CI.


## CI, rollout, and rollback checks for specimen-list Side/Portion inference

When releasing inference changes, run and capture these checks:

```bash
pytest --maxfail=1
pytest --cov=app/cms --cov-report=term-missing
python app/manage.py makemigrations --check
python app/manage.py migrate --check
```

### Runtime toggle
- Setting: `SPECIMEN_LIST_ENABLE_SIDE_PORTION_INFERENCE`
- Use `True` for normal operation.
- Set `False` for immediate rollback if inference quality issues are observed.

### Staging verification matrix
Validate representative tokens before production rollout:
- `Lt femur Dist` => `left`, `distal`
- `Rt humerus Prox` => `right`, `proximal`
- `Left tibia` => `left`, no inferred portion
- `Prox radius` => no inferred side, `proximal`
- `Lt Rt ulna` => ambiguous side; no side inferred

### Docs tooling note
If a docs verification workflow attempts to run MkDocs, skip that specific step and document the skip reason in the PR because project documentation is Markdown-only under `/docs`.
