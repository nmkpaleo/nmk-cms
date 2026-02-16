from pathlib import Path

from importlib import util


MODULE_PATH = Path(__file__).resolve().parents[2] / "docs" / "scripts" / "update_prompts.py"
SPEC = util.spec_from_file_location("update_prompts", MODULE_PATH)
assert SPEC and SPEC.loader  # narrow mypy/ruff hints
update_prompts = util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_prompts)  # type: ignore[union-attr]

ADDITIONAL_CATEGORY = update_prompts.ADDITIONAL_CATEGORY
START_MARKER = update_prompts.START_MARKER
END_MARKER = update_prompts.END_MARKER
categorize_requirements = update_prompts.categorize_requirements
load_requirements = update_prompts.load_requirements
render_dependency_section = update_prompts.render_dependency_section
update_prompt_file = update_prompts.update_prompt_file


def test_load_requirements_deduplicates_and_skips_comments(tmp_path: Path) -> None:
    requirements_txt = tmp_path / "requirements.txt"
    requirements_txt.write_text(
        "\n".join(
            [
                "# comment",  # ignored
                "Django==4.2.26",
                "django==4.2.27",  # ignored because duplicate name
                "plotly",  # retained
            ]
        )
    )

    parsed = load_requirements(requirements_txt)

    assert parsed["django"] == "Django==4.2.26"
    assert parsed["plotly"] == "plotly"
    assert "# comment" not in parsed.values()


def test_categorize_and_render_section_includes_additional_category(tmp_path: Path) -> None:
    requirements = {
        "django": "Django==4.2.26",
        "celery": "celery==5.4.0",
    }

    categories = categorize_requirements(requirements)
    section = render_dependency_section(categories)

    assert "### Core Framework & Runtime" in section
    assert "- Django == 4.2.26" in section
    assert f"### {ADDITIONAL_CATEGORY}" in section
    assert "- celery == 5.4.0" in section
    assert "docs/scripts/update_prompts.py" in section


def test_update_prompt_file_replaces_snapshot_block(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text(
        f"Intro\n{START_MARKER}\n\nOld data\n\n{END_MARKER}\nOutro\n"
    )

    new_section = "### Sample\n- Package == 1.0\n\n> note"
    update_prompt_file(prompt_path, new_section)

    updated = prompt_path.read_text()

    assert "Old data" not in updated
    assert "### Sample" in updated
    assert updated.count(START_MARKER) == 1
    assert updated.count(END_MARKER) == 1
