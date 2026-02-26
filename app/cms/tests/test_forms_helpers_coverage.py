from io import BytesIO
import zipfile

import pytest

from cms.forms import (
    _column_index_from_reference,
    _read_cell_value,
    _trim_empty_columns,
    _load_xlsx_dataset,
    dataset_to_rows,
    ManualImportFailure,
    ManualImportSummary,
)


def test_column_index_from_reference_handles_basic_cases():
    assert _column_index_from_reference(None) == 0
    assert _column_index_from_reference("A1") == 0
    assert _column_index_from_reference("C12") == 2
    assert _column_index_from_reference("AA20") == 26



def test_trim_empty_columns_removes_only_trailing_empty_columns():
    rows = [["id", "name", ""], ["1", "Alpha", ""]]
    assert _trim_empty_columns(rows) == [["id", "name"], ["1", "Alpha"]]
    assert _trim_empty_columns([["", ""], ["", ""]]) == []


def test_read_cell_value_supports_inline_shared_bool_and_string():
    from xml.etree import ElementTree as ET

    inline = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="inlineStr"><is><t>Hello</t></is></c>')
    assert _read_cell_value(inline, []) == "Hello"

    shared = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="s"><v>1</v></c>')
    assert _read_cell_value(shared, ["Zero", "One"]) == "One"

    boolean = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="b"><v>1</v></c>')
    assert _read_cell_value(boolean, []) == "TRUE"

    plain = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><v>42</v></c>')
    assert _read_cell_value(plain, []) == "42"


def test_load_xlsx_dataset_reads_simple_workbook_bytes():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            """
            <workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"
                      xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">
              <sheets>
                <sheet name=\"Sheet1\" sheetId=\"1\" r:id=\"rId1\" />
              </sheets>
            </workbook>
            """,
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """
            <Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
              <Relationship Id=\"rId1\" Type=\"worksheet\" Target=\"worksheets/sheet1.xml\" />
            </Relationships>
            """,
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            """
            <worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">
              <sheetData>
                <row r=\"1\"><c r=\"A1\" t=\"str\"><v>id</v></c><c r=\"B1\" t=\"str\"><v>name</v></c></row>
                <row r=\"2\"><c r=\"A2\"><v>1</v></c><c r=\"B2\" t=\"str\"><v>Alpha</v></c></row>
              </sheetData>
            </worksheet>
            """,
        )
    dataset = _load_xlsx_dataset(buffer.getvalue())
    assert dataset.headers == ["id", "name"]
    assert dataset.dict[0]["id"] == "1"
    assert dataset.dict[0]["name"] == "Alpha"


def test_dataset_to_rows_validates_required_id_column():
    from tablib import Dataset

    dataset = Dataset(headers=["name"]) 
    dataset.append(["Alpha"])
    with pytest.raises(ValueError, match="id"):
        dataset_to_rows(dataset)


def test_manual_import_summary_build_error_report():
    summary = ManualImportSummary(total_rows=2, failures=[ManualImportFailure(2, "x", "bad")])
    report = summary.build_error_report()
    assert "row_number,identifier,message" in report
    assert "2,x,bad" in report
    assert summary.error_count == 1
