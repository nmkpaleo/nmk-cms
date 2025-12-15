from cms.manual_import import build_accession_payload, build_row_section


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
        "body_parts": "left tibia",
        "fragments": "5",
    }

    section = build_row_section(row, "C")
    natures = _extract_nature_values(section)

    assert len(natures) == 1
    assert natures[0]["verbatim_element"]["interpreted"] == "left tibia"
    assert natures[0]["side"]["interpreted"] == "Left"
    assert natures[0]["fragments"]["interpreted"] == "5"


def test_unlabeled_parts_stored_in_note_when_labels_present():
    rows = [
        {
            "accession_number": "KNM-123 A-B",
            "body_parts": "A: upper molar; B: broken mandible; vertebrae",
        }
    ]

    payload = build_accession_payload(rows)
    accession = payload["accessions"][0]
    additional_notes = accession["additional_notes"]

    assert any("vertebrae" in (note.get("value") or {}).get("interpreted", "") for note in additional_notes)

    rows_payload = accession["rows"]
    assert _extract_nature_values(rows_payload[0])[0]["verbatim_element"]["interpreted"] == "upper molar"
    assert _extract_nature_values(rows_payload[1])[0]["verbatim_element"]["interpreted"] == "broken mandible"


def test_unlabeled_parts_with_multiple_suffixes_assigned_to_first():
    rows = [
        {
            "accession_number": "KNM-456 A-B",
            "body_parts": "humerus",
        }
    ]

    payload = build_accession_payload(rows)
    accession = payload["accessions"][0]
    manual_metadata = payload.get("_manual_import_metadata", {})

    assert manual_metadata.get("body_part_resolution", {}).get("strategy") == "unlabeled_first_suffix"

    first_row_natures = _extract_nature_values(accession["rows"][0])
    assert first_row_natures[0]["verbatim_element"]["interpreted"] == "humerus"

    second_row_natures = _extract_nature_values(accession["rows"][1])
    second_verbatim = second_row_natures[0].get("verbatim_element")
    assert second_verbatim is None or second_verbatim.get("interpreted") is None

    note_values = [
        (note.get("value") or {}).get("interpreted", "") for note in accession["additional_notes"]
    ]
    assert any("humerus" in value for value in note_values)
