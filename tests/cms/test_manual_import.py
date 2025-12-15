from cms.manual_import import build_row_section


def _extract_nature_values(section: dict) -> list[dict]:
    return section.get("natures") or []


def test_build_row_section_uses_labeled_body_parts_for_matching_suffix():
    row = {
        "body_parts": "A: upper molar; B: broken mandible; C: upper premolars P3-P4",
    }

    section = build_row_section(row, "B")
    natures = _extract_nature_values(section)

    assert len(natures) == 1
    assert natures[0]["verbatim_element"]["interpreted"] == "broken mandible"


def test_build_row_section_falls_back_to_unlabeled_when_no_match():
    row = {
        "body_parts": "A: skull; left tibia",
        "fragments": "5",
    }

    section = build_row_section(row, "C")
    natures = _extract_nature_values(section)

    assert len(natures) == 1
    assert natures[0]["verbatim_element"]["interpreted"] == "left tibia"
    assert natures[0]["side"]["interpreted"] == "Left"
    assert natures[0]["fragments"]["interpreted"] == "5"
