from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_user_quality_control_docs_cover_structured_field_slip_review() -> None:
    content = _read("docs/user/quality-control.md")

    assert "Reviewing structured field-slip metadata" in content
    assert "fragments (integer-only interpretation)" in content
    assert "Rollout and rollback notes" in content


def test_admin_fieldslip_docs_cover_qc_approval_checks() -> None:
    content = _read("docs/admin/fieldslips.md")

    assert "QC approval ingestion checks" in content
    assert "curators" in content.lower()
    assert "duplicate `AccessionFieldSlip`" in content


def test_development_rollout_doc_avoids_mkdocs_commands() -> None:
    content = _read("docs/development/field_slip_qc_rollout.md")

    assert "Do not run MkDocs commands" in content
    assert "python -m pytest tests/docs" in content
    assert "python manage.py makemigrations --check --dry-run" in content
