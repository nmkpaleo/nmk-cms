"""Synchronize dependency snapshots in developer prompt documentation."""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, OrderedDict as OrderedDictType

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = REPO_ROOT / "app" / "requirements.txt"
PROMPT_FILES = [
    REPO_ROOT / "docs" / "development" / "codex_prompt.md",
    REPO_ROOT / "docs" / "development" / "coding prompt template.md",
]
START_MARKER = "<!-- DEPENDENCY_SNAPSHOT:START -->"
END_MARKER = "<!-- DEPENDENCY_SNAPSHOT:END -->"
NOTE_LINE = (
    "> ℹ️ **Automation note:** Run `python docs/scripts/update_prompts.py` after editing "
    "`app/requirements.txt` to regenerate this dependency snapshot."
)

CATEGORY_RULES: "OrderedDictType[str, Iterable[str]]" = OrderedDict(
    [
        (
            "Core Framework & Runtime",
            (
                "django",
                "asgiref",
                "sqlparse",
                "gunicorn",
                "debugpy",
                "watchdog",
            ),
        ),
        (
            "Database, Caching & State",
            (
                "mysqlclient",
                "django-redis",
                "django-userforeignkey",
            ),
        ),
        (
            "Auth, Security & Identity",
            (
                "django-allauth",
                "oauthlib",
                "requests-oauthlib",
                "python3-openid",
                "pyjwt",
            ),
        ),
        (
            "Data Integrity, Import & Auditing",
            (
                "django-simple-history",
                "django-import-export",
                "django-crum",
            ),
        ),
        (
            "Forms, UI & Filtering",
            (
                "django-filter",
                "django-formtools",
                "django-autocomplete-light",
                "django-select2",
                "pillow",
            ),
        ),
        (
            "APIs, Networking & Utilities",
            (
                "requests",
                "urllib3",
                "idna",
                "python-dotenv",
            ),
        ),
        (
            "Analytics, AI & Matching",
            (
                "openai",
                "plotly",
                "numpy",
                "pandas",
                "matplotlib",
                "seaborn",
                "python-levenshtein",
                "rapidfuzz",
            ),
        ),
    ]
)
ADDITIONAL_CATEGORY = "Additional Dependencies"
CATEGORY_LOOKUP = {
    package: category
    for category, packages in CATEGORY_RULES.items()
    for package in packages
}


def normalize_requirement_name(requirement: str) -> str:
    parts = re.split(r"[<>=!~\s]", requirement.strip(), maxsplit=1)
    return parts[0].lower() if parts and parts[0] else ""


def format_requirement(requirement: str) -> str:
    requirement = requirement.strip()
    for operator in ("==", ">=", "<=", "~=", "!="):
        if operator in requirement:
            name, version = requirement.split(operator, 1)
            return f"{name.strip()} {operator} {version.strip()}"
    return f"{requirement} (unpinned)"


def load_requirements(path: Path) -> Dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Requirements file not found: {path}")
    requirements: Dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        normalized = normalize_requirement_name(stripped)
        if not normalized:
            continue
        if normalized not in requirements:
            requirements[normalized] = stripped
    return requirements


def categorize_requirements(requirements: Mapping[str, str]) -> "OrderedDictType[str, List[str]]":
    buckets: "OrderedDictType[str, List[str]]" = OrderedDict(
        (category, []) for category in CATEGORY_RULES.keys()
    )
    additional: List[str] = []
    for normalized_name, raw_requirement in sorted(requirements.items()):
        formatted = format_requirement(raw_requirement)
        category = CATEGORY_LOOKUP.get(normalized_name)
        if category:
            buckets[category].append(formatted)
        else:
            additional.append(formatted)
    if additional:
        buckets[ADDITIONAL_CATEGORY] = additional
    return OrderedDict((key, value) for key, value in buckets.items() if value)


def render_dependency_section(categories: "OrderedDictType[str, List[str]]") -> str:
    lines: List[str] = []
    for category, packages in categories.items():
        lines.append(f"### {category}")
        for package in sorted(packages, key=str.lower):
            lines.append(f"- {package}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    if lines:
        lines.append("")
    lines.append(NOTE_LINE)
    return "\n".join(lines)


def update_prompt_file(prompt_path: Path, rendered_section: str) -> None:
    content = prompt_path.read_text()
    if START_MARKER not in content or END_MARKER not in content:
        raise ValueError(
            f"Missing dependency snapshot markers in {prompt_path.relative_to(REPO_ROOT)}"
        )
    replacement = (
        f"{START_MARKER}\n\n{rendered_section.strip()}\n\n{END_MARKER}"
    )
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        flags=re.DOTALL,
    )
    updated = pattern.sub(replacement, content)
    prompt_path.write_text(updated.rstrip() + "\n")


def main() -> None:
    requirements = load_requirements(REQUIREMENTS_PATH)
    categories = categorize_requirements(requirements)
    rendered = render_dependency_section(categories)
    for prompt_file in PROMPT_FILES:
        update_prompt_file(prompt_file, rendered)


if __name__ == "__main__":
    main()
