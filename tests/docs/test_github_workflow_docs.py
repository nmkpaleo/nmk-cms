from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_github_workflow_policy_is_linked_from_core_guides() -> None:
    workflow_path = ROOT / "docs/development/github-workflow.md"

    assert workflow_path.is_file()
    assert "github-workflow.md" in _read("README.md")
    assert "github-workflow.md" in _read("CONTRIBUTING.md")
    assert "github-workflow.md" in _read("SECURITY.md")
    assert "github-workflow.md" in _read("docs/development/README.md")


def test_github_workflow_policy_matches_ci_baseline() -> None:
    workflow = _read("docs/development/github-workflow.md")
    release = _read("docs/development/release-checklist.md")
    copilot = _read(".github/copilot-instructions.md")

    assert "CI / test" in workflow
    assert "70% coverage floor" in workflow
    assert "--cov-fail-under=70" in release
    assert "Django:** 5.2 LTS" in copilot
    assert "Django:** 4.2.25" not in copilot


def test_documentation_policy_remains_markdown_only() -> None:
    readme = _read("README.md")
    workflow = _read("docs/development/github-workflow.md")

    assert "does not use\nMkDocs" in readme
    assert "mkdocs build" not in workflow.lower()


def test_publishing_jobs_use_protected_environments() -> None:
    production = _read(".github/workflows/production-ci.yml")
    staging = _read(".github/workflows/staging-ci.yml")
    automation = _read("docs/development/automation.md")

    assert "    environment: production" in production
    assert "    environment: staging" in staging
    assert "prevents\n  self-approval" in automation
