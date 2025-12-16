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


def test_inline_labeled_body_parts_with_equals_and_parentheses():
    rows = [
        {
            "accession_number": "KNM-789 A-D",
            "body_parts": "A = frag proximal right humerus B = prox. right ulna C = distal left radius D = frags ulna ?(3) shaft",
        }
    ]

    payload = build_accession_payload(rows)
    accession_rows = payload["accessions"][0]["rows"]

    expected = [
        "frag proximal right humerus",
        "prox. right ulna",
        "distal left radius",
        "frags ulna ?(3) shaft",
    ]

    for section, verbatim in zip(accession_rows, expected):
        natures = _extract_nature_values(section)
        assert natures[0]["verbatim_element"]["interpreted"] == verbatim


def test_inline_labeled_body_parts_with_parentheses_and_and_delimiters():
    rows = [
        {
            "accession_number": "KNM-780 A-D",
            "body_parts": "(A) frag. proximal right humerus (B) prox. right ulna and (C) distal Rt. radius (D) frags ulna? shaft",
        }
    ]

    payload = build_accession_payload(rows)
    accession_rows = payload["accessions"][0]["rows"]

    expected = [
        "frag. proximal right humerus",
        "prox. right ulna",
        "distal Rt. radius",
        "frags ulna? shaft",
    ]

    for section, verbatim in zip(accession_rows, expected):
        natures = _extract_nature_values(section)
        assert natures[0]["verbatim_element"]["interpreted"] == verbatim


def test_inline_labeled_body_parts_with_equals_and_newline():
    rows = [
        {
            "accession_number": "KNM-781 A-B",
            "body_parts": "A= Juvenile distorted male cranium lacking tooth crowns. B= skull frags (8)\n",
        }
    ]

    payload = build_accession_payload(rows)
    accession_rows = payload["accessions"][0]["rows"]

    expected = [
        "Juvenile distorted male cranium lacking tooth crowns.",
        "skull frags (8)",
    ]

    for section, verbatim in zip(accession_rows, expected):
        natures = _extract_nature_values(section)
        assert natures[0]["verbatim_element"]["interpreted"] == verbatim


def test_inline_labeled_body_parts_expand_suffixes_when_missing():
    rows = [
        {
            "accession_number": "KNM-783",
            "body_parts": "A=md frag m1 or m3, B=lt. p3",
        }
    ]

    payload = build_accession_payload(rows)
    accession_rows = payload["accessions"][0]["rows"]

    assert len(accession_rows) == 2
    assert _extract_nature_values(accession_rows[0])[0]["verbatim_element"]["interpreted"] == "md frag m1 or m3"
    assert _extract_nature_values(accession_rows[1])[0]["verbatim_element"]["interpreted"] == "lt. p3"


def test_invalid_body_part_labels_ignored_for_suffix_derivation():
    rows = [
        {
            "accession_number": "KNM-986",
            "body_parts": "A= humerus 1= ulna",
        }
    ]

    payload = build_accession_payload(rows)
    accession = payload["accessions"][0]
    accession_rows = accession["rows"]

    assert len(accession_rows) == 1
    natures = _extract_nature_values(accession_rows[0])
    assert natures[0]["verbatim_element"]["interpreted"] == "humerus"

    note_values = [
        (note.get("value") or {}).get("interpreted", "") for note in accession["additional_notes"]
    ]
    assert any("ignored" in value and "1" in value for value in note_values)

    manual_metadata = payload.get("_manual_import_metadata", {})
    resolution_metadata = manual_metadata.get("body_part_resolution", {})
    assert resolution_metadata.get("invalid_labels") == ["1"]


def test_only_invalid_body_part_labels_fall_back_to_default_suffix():
    rows = [
        {
            "accession_number": "KNM-987",
            "body_parts": "1= tibia; 2= femur",
        }
    ]

    payload = build_accession_payload(rows)
    accession = payload["accessions"][0]
    accession_rows = accession["rows"]

    assert len(accession_rows) == 1
    section = accession_rows[0]
    assert (section.get("specimen_suffix") or {}).get("interpreted") == "-"

    natures = _extract_nature_values(section)
    verbatim_elements = [
        (nature.get("verbatim_element") or {}).get("interpreted") for nature in natures
    ]
    assert verbatim_elements == ["tibia", "femur"]

    note_values = [
        (note.get("value") or {}).get("interpreted", "") for note in accession["additional_notes"]
    ]
    assert any("ignored" in value and "1" in value and "2" in value for value in note_values)

    manual_metadata = payload.get("_manual_import_metadata", {})
    resolution_metadata = manual_metadata.get("body_part_resolution", {})
    assert resolution_metadata.get("invalid_labels") == ["1", "2"]


def test_inline_labeled_body_parts_with_period_delimiters():
    rows = [
        {
            "accession_number": "KNM-782 A-B",
            "body_parts": "A. Lt femur, B. scapula frag.",
        }
    ]

    payload = build_accession_payload(rows)
    accession_rows = payload["accessions"][0]["rows"]

    expected = [
        "Lt femur",
        "scapula frag.",
    ]

    for section, verbatim in zip(accession_rows, expected):
        natures = _extract_nature_values(section)
        assert natures[0]["verbatim_element"]["interpreted"] == verbatim


def test_other_field_labeled_body_parts_build_accession_rows():
    rows = [
        {
            "accession_number": "KNM-900",
            "other": (
                "D. distal Rt. humerus | E. Mand. frag erupting p2 | F. Mand. frag dm2 m1 | "
                "G. Rt. prox. femur | H. Rt. prox. humerus | I. Rt. mandibulus condyle | "
                "J. bone grag. probably distal tibia (Rt. humerus shaft, dist. Lt. tibia shaft)"
            ),
        }
    ]

    payload = build_accession_payload(rows)
    accession = payload["accessions"][0]
    accession_rows = accession["rows"]

    expected_suffixes = ["D", "E", "F", "G", "H", "I", "J"]
    expected_verbatims = [
        "distal Rt. humerus",
        "Mand. frag erupting p2",
        "Mand. frag dm2 m1",
        "Rt. prox. femur",
        "Rt. prox. humerus",
        "Rt. mandibulus condyle",
        "bone grag. probably distal tibia (Rt. humerus shaft, dist. Lt. tibia shaft)",
    ]

    assert [
        (section.get("specimen_suffix") or {}).get("interpreted") for section in accession_rows
    ] == expected_suffixes

    for section, verbatim in zip(accession_rows, expected_verbatims):
        natures = _extract_nature_values(section)
        assert natures[0]["verbatim_element"]["interpreted"] == verbatim

    note_values = [
        (note.get("value") or {}).get("interpreted", "") for note in accession["additional_notes"]
    ]

    assert not any("D. distal Rt. humerus" in value for value in note_values)


def test_other_field_without_labels_remains_comment():
    rows = [
        {
            "accession_number": "KNM-901",
            "body_parts": "humerus",
            "other": "Unlabeled context that should stay as a note",
        }
    ]

    payload = build_accession_payload(rows)
    accession = payload["accessions"][0]
    note_values = [
        (note.get("value") or {}).get("interpreted", "") for note in accession["additional_notes"]
    ]

    assert any("Unlabeled context" in value for value in note_values)


def test_inline_labeled_body_parts_with_comma_delimiters():
    rows = [
        {
            "accession_number": "KNM-784",
            "body_parts": "A, Lt m3; B, m1; C, Lp3; D, Rp3; E, Lt C female F, root.",
        }
    ]

    payload = build_accession_payload(rows)
    accession_rows = payload["accessions"][0]["rows"]

    expected = [
        "Lt m3",
        "m1",
        "Lp3",
        "Rp3",
        "Lt C female",
        "root.",
    ]

    assert len(accession_rows) == len(expected)
    for section, verbatim in zip(accession_rows, expected):
        natures = _extract_nature_values(section)
        assert natures[0]["verbatim_element"]["interpreted"] == verbatim


def test_inline_labeled_body_parts_with_pipe_delimiters():
    rows = [
        {
            "accession_number": "KNM-785",
            "body_parts": "A = Lt m3, | B = m1 | C = Lp3 | D = Rp3 | E = Lt c female | F = root\n",
        }
    ]

    payload = build_accession_payload(rows)
    accession_rows = payload["accessions"][0]["rows"]

    expected = [
        "Lt m3",
        "m1",
        "Lp3",
        "Rp3",
        "Lt c female",
        "root",
    ]

    assert len(accession_rows) == len(expected)
    for section, verbatim in zip(accession_rows, expected):
        natures = _extract_nature_values(section)
        assert natures[0]["verbatim_element"]["interpreted"] == verbatim


def test_verbatim_element_truncated_and_added_to_notes():
    long_body_part = "A: " + "very long description " * 20

    rows = [
        {
            "accession_number": "KNM-900 A-B",
            "body_parts": long_body_part,
        }
    ]

    payload = build_accession_payload(rows)
    accession = payload["accessions"][0]
    first_row_nature = _extract_nature_values(accession["rows"][0])[0]

    verbatim_value = first_row_nature["verbatim_element"]["interpreted"]
    assert len(verbatim_value) == 255

    note_values = [
        (note.get("value") or {}).get("interpreted", "")
        for note in accession["additional_notes"]
    ]
    assert any("very long description" in value for value in note_values)


def test_aerial_photo_strips_labels_before_storage():
    rows = [
        {
            "accession_number": "KNM-910",
            "body_parts": "A: tibia",
            "photo_id": "Aerial Photo 1430/019 - 114 ",
        }
    ]

    payload = build_accession_payload(rows)
    slip = payload["accessions"][0]["field_slips"][0]

    assert (slip.get("aerial_photo") or {}).get("interpreted") == "1430/019 - 114"


def test_aerial_photo_truncated_and_noted_when_too_long():
    long_photo = "Aerial Photo " + ("X" * 30)

    rows = [
        {
            "accession_number": "KNM-911",
            "body_parts": "A: femur",
            "photo_id": long_photo,
        }
    ]

    payload = build_accession_payload(rows)
    accession = payload["accessions"][0]
    slip = accession["field_slips"][0]

    aerial_photo_value = (slip.get("aerial_photo") or {}).get("interpreted")
    assert aerial_photo_value is not None
    assert len(aerial_photo_value) == 25

    note_values = [
        (note.get("value") or {}).get("interpreted", "")
        for note in accession["additional_notes"]
    ]
    assert any("Full aerial photo text" in value for value in note_values)
