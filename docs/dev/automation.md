# Prompt Automation Reference

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

## Maintenance
- Update `CATEGORY_RULES` in `docs/scripts/update_prompts.py` when introducing new dependency groups so related packages are
  grouped meaningfully.
- When reorganising prompt content, preserve the dependency markers so the automation can continue to refresh the section.
