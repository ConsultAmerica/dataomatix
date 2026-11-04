"""Extracted Data for structured documents: sections, clauses, paragraphs
and tables with their own text, the table of contents left out — one
dataset for the view and the Excel export (services/clause_outline.py)."""

from __future__ import annotations

import io

import openpyxl

from app.services.clause_outline import build_outline, build_outline_xlsx

DOTS = " " + "." * 40 + " "

SOLICITATION = [
    (1, "BMO Small Business Solicitation\nRequest for Proposal"),
    (2, "Table of Contents\n" + "\n".join(f"  {n}{DOTS}{p}" for n, p in [
        ("Section B Services, Ordering and Prices", 3), ("B.1 Background", 3), ("B.1.1 Authority", 3),
        ("B.1.2 Contract Type", 3), ("B.1.4 Contract Access Fee (CAF)", 4), ("B.2 Task Order Pricing", 4),
        ("C.5 Service Category Descriptions", 5), ("C.5.1 Operations & Maintenance", 5),
        ("C.5.1.1 HVAC Maintenance (Required Service)", 5), ("C.5.1.2 Plumbing and Pipefitting (Required Service)", 5),
    ])),
    (3, "Section B Services, Ordering and Prices\n\nB.1 Background\n\nStrategic Sourcing was mandated by the Office of\n"
        "Management and Budget.\n\nB.1.1 Authority\n\nThe Administrator of GSA is authorized to purchase supplies\n\n"
        "B.1.2 Contract Type\n\nBMO SB is a family of Multiple Award contracts that runs on to\n                 Page 3 of 9"),
    (4, "the next page without a break.\n\nB.1.4 Contract Access Fee (CAF)\n\nGSA operating costs.\n\n"
        "B.2 Task Order Pricing\n\nAgencies determine fair and reasonable prices.\n"
        "C.5.1     Operations & Maintenance     Required     Monthly report\n"),
    (5, "Section C - Description/Specifications\n\nC.5 Service Category Descriptions\n\nC.5.1 Operations & Maintenance\n\n"
        "C.5.1.1 HVAC Maintenance (Required Service)\n\nHeating, ventilation and air conditioning.\n\n"
        "C.5.1.2 Plumbing and Pipefitting (Required Service)\n\nPlumbing systems."),
]


def _records(outline: dict) -> list[dict]:
    """Each record as {column label: value}, with its kind and number."""

    labels = [column["label"] for column in outline["columns"]]
    return [{"kind": record["kind"], "number": record["number"], **dict(zip(labels, record["cells"]))} for record in outline["records"]]


def _row(outline: dict, number: str) -> dict:
    return next(record for record in _records(outline) if record["number"] == number and not record["kind"].startswith("table"))


def test_contents_pages_are_left_out_and_each_heading_keeps_its_own_text():
    outline = build_outline(SOLICITATION)
    assert outline["style"] == "numbered"
    assert outline["contents_pages"] == [2]
    assert not any("....." in row["Full Content"] for row in _records(outline))
    assert [column["label"] for column in outline["columns"]] == [
        "Section Number", "Paragraph Number", "Heading", "Full Content", "PDF Page", "Parent Clause"]
    background = _row(outline, "B.1")
    assert (background["Section Number"], background["Paragraph Number"], background["Parent Clause"], background["Heading"]) == (
        "B.1", "", "Section B", "Background")
    # The lines the PDF wrapped are one paragraph again.
    assert background["Full Content"] == "Strategic Sourcing was mandated by the Office of Management and Budget."
    assert background["PDF Page"] == "3"
    assert _row(outline, "B.1.1")["Parent Clause"] == "B.1"


def test_nested_clauses_name_their_parent():
    outline = build_outline(SOLICITATION)
    hvac = _row(outline, "C.5.1.1")
    assert (hvac["Section Number"], hvac["Paragraph Number"], hvac["Parent Clause"], hvac["Heading"]) == (
        "C.5", "C.5.1.1", "C.5.1", "HVAC Maintenance (Required Service)")
    assert hvac["Full Content"] == "Heating, ventilation and air conditioning."
    assert _row(outline, "C.5.1")["Parent Clause"] == "C.5"


def test_a_clause_runs_on_across_the_page_break_without_the_footer():
    contract_type = _row(build_outline(SOLICITATION), "B.1.2")
    assert contract_type["PDF Page"] == "3–4"
    assert "Page 3 of 9" not in contract_type["Full Content"]
    assert contract_type["Full Content"].endswith("runs on to the next page without a break.")


def test_a_table_row_that_starts_with_a_clause_number_is_not_a_heading():
    outline = build_outline(SOLICITATION)
    assert [row["number"] for row in _records(outline)].count("C.5.1") == 1
    assert "C.5.1     Operations & Maintenance     Required" in _row(outline, "B.2")["Full Content"]


def test_missing_clauses_are_reported_not_filled_in():
    outline = build_outline(SOLICITATION)
    gaps = [check for check in outline["checks"] if check["code"] == "sequence_gap"]
    assert [check["number"] for check in gaps] == ["B.1.3"]
    assert "B.1.3" not in {row["number"] for row in _records(outline)}


def test_every_word_of_the_body_is_in_a_row():
    coverage = build_outline(SOLICITATION)["coverage"]
    assert coverage["missing_words"] == 0 and coverage["body_words"] > 50


def test_a_contents_entry_missing_from_the_body_is_reported():
    pages = [*SOLICITATION[:4], (5, SOLICITATION[4][1].replace("C.5.1.2 Plumbing and Pipefitting (Required Service)\n\nPlumbing systems.", ""))]
    checks = build_outline(pages)["checks"]
    assert any(check["code"] == "not_in_body" and check["number"] == "C.5.1.2" for check in checks)


FAR = [
    (1, "Part 7 - Acquisition Planning\n\n7.000 Scope of part.\n\nSubpart 7.1 - Acquisition Plans\n\n7.101 Definitions.\n\n"
        "7.102 Policy.\n\nParent topic: Federal Acquisition Regulation\n\n7.000 Scope of part.\n\n"
        "This part prescribes policies and procedures for-\n\n(a) Developing acquisition plans;\n\n"
        "(b) Determining whether to use commercial or Government resources for acquisition of supplies or\nservices;\n\n"
        "Subpart 7.1 - Acquisition Plans\n\n7.101 Definitions.\n\nAs used in this subpart-\n\n"
        "Life-cycle cost means the total cost to the Government of acquiring"),
    (2, "and operating the items.\n\n7.102 Policy.\n\n(a) Agencies shall perform acquisition planning and conduct market research.\n\n"
        "(1) Acquisition of commercial products; and\n\n(c) This planning shall integrate the efforts of all personnel."),
]


def test_far_sections_have_a_row_per_lettered_paragraph():
    outline = build_outline(FAR)
    assert outline["style"] == "far"
    assert [column["label"] for column in outline["columns"]] == [
        "Section Number", "Paragraph Number", "Heading", "Full Content", "PDF Page", "Subpart"]
    rows = [(row["Section Number"], row["Paragraph Number"], row["Heading"], row["Full Content"], row["Subpart"]) for row in _records(outline)]
    assert rows[:3] == [
        ("7.000", "", "Scope of part", "This part prescribes policies and procedures for-", ""),
        ("7.000", "(a)", "", "Developing acquisition plans;", ""),
        ("7.000", "(b)", "", "Determining whether to use commercial or Government resources for acquisition of supplies or services;", ""),
    ]
    definitions = _row(outline, "7.101")
    assert (definitions["Heading"], definitions["Subpart"]) == ("Definitions", "Subpart 7.1 - Acquisition Plans")
    # A subpart without text of its own is no separate row: its title is in the Subpart column.
    assert not any(row["number"].startswith("Subpart") for row in _records(outline))
    # Run on across the page break, joined back.
    assert definitions["Full Content"].endswith("of acquiring and operating the items.")
    policy = [row for row in _records(outline) if row["Section Number"] == "7.102" and row["kind"] == "paragraph"]
    # "(1)" stays inside "(a)"; "(b)" isn't there, so "(c)" is reported.
    assert [row["Paragraph Number"] for row in policy] == ["(a)", "(c)"]
    assert policy[0]["Subpart"] == "Subpart 7.1 - Acquisition Plans"
    assert "(1) Acquisition of commercial products" in policy[0]["Full Content"]
    assert any(check["number"] == "7.102(b)" for check in outline["checks"])
    assert outline["coverage"]["missing_words"] == 0


def test_text_without_numbered_sections_has_no_outline():
    assert build_outline([(1, "Dear customer,\n\nThank you for your order.")])["style"] == "none"


TABLE = {"kind": "table", "record_key": "table:4:0", "title": "Deliverables", "pages": [4],
         "headers": ["Clause", "Deliverable", "Due"],
         "rows": [{"page": 4, "cells": ["G.3.8", "Mergers notice", "30 days"]}, {"page": 4, "cells": ["G.3.9", "FAPIIS update", "Monthly"]}]}


def _with_table() -> list[tuple[int, str]]:
    return [*SOLICITATION[:3], (4, SOLICITATION[3][1].replace(
        "Agencies determine fair and reasonable prices.\n",
        "Agencies determine fair and reasonable prices.\nClause     Deliverable        Due\n"
        "G.3.8      Mergers notice     30 days\nG.3.9      FAPIIS update      Monthly\n")), SOLICITATION[4]]


def test_a_table_is_placed_under_its_clause_with_a_column_per_table_column():
    outline = build_outline(_with_table(), [TABLE])
    labels = [column["label"] for column in outline["columns"]]
    assert labels[-3:] == ["Table Column 1", "Table Column 2", "Table Column 3"]
    records = _records(outline)
    at = next(index for index, row in enumerate(records) if row["number"] == "B.2" and row["kind"] == "clause")
    header, first, second = records[at + 1:at + 4]
    assert (header["kind"], header["Heading"], header["Full Content"], header["PDF Page"]) == ("table_header", "Table 1", "Deliverables", "4")
    assert [header[f"Table Column {n}"] for n in (1, 2, 3)] == ["Clause", "Deliverable", "Due"]
    assert [first[f"Table Column {n}"] for n in (1, 2, 3)] == ["G.3.8", "Mergers notice", "30 days"]
    assert (second["kind"], second["Section Number"], second["Paragraph Number"]) == ("table_row", "B.2", "")
    # The table's lines aren't in the clause text a second time; nothing is lost.
    content = records[at]["Full Content"]
    assert "Mergers notice" not in content and "[Table 1 — in the rows below]" in content
    assert content.startswith("Agencies determine fair and reasonable prices.")
    assert outline["coverage"]["missing_words"] == 0


def test_table_lines_with_other_words_stay_in_the_clause_text():
    table = {**TABLE, "rows": TABLE["rows"][:1]}  # the table holds only one of the two printed rows
    outline = build_outline(_with_table(), [table])
    assert "FAPIIS update" in _row(outline, "B.2")["Full Content"]
    assert outline["coverage"]["missing_words"] == 0


def test_one_worksheet_per_document_with_the_same_columns_and_rows_as_the_view():
    first = build_outline(_with_table(), [TABLE])
    second = build_outline(FAR)
    workbook = openpyxl.load_workbook(io.BytesIO(build_outline_xlsx([("bmo.pdf", first), ("Part-7.pdf", second)])))
    assert workbook.sheetnames == ["bmo", "Part-7", "Checks"]
    for name, outline in (("bmo", first), ("Part-7", second)):
        sheet = workbook[name]
        assert [cell.value for cell in sheet[4]] == [column["label"] for column in outline["columns"]]
        written = [[cell.value or "" for cell in row] for row in sheet.iter_rows(min_row=5)]
        assert written == [[value or "" for value in record["cells"]] for record in outline["records"]]
        assert sheet.freeze_panes == "A5" and sheet.auto_filter.ref.startswith("A4:")


def test_the_excel_export_keeps_long_text_whole_in_continuation_rows():
    long_text = "word " * 9000  # 45,000 characters: more than one Excel cell holds
    pages = [*SOLICITATION[:4], (5, SOLICITATION[4][1] + "\n\nC.5.1.3 Electrical Maintenance (Required Service)\n\n" + long_text)]
    outline = build_outline(pages)
    workbook = openpyxl.load_workbook(io.BytesIO(build_outline_xlsx([("bmo.pdf", outline)])))
    assert workbook.sheetnames == ["Extracted Data", "Checks"]
    rows = [[cell.value for cell in row] for row in workbook["Extracted Data"].iter_rows(min_row=5)]
    electrical = [row for row in rows if row[1] == "C.5.1.3"]
    assert [row[2] for row in electrical] == ["Electrical Maintenance (Required Service)",
                                             "Electrical Maintenance (Required Service) (continued 2 of 2)"]
    assert "".join(row[3] for row in electrical) == long_text.strip()
    assert workbook["Checks"].max_row >= 5


def test_wrapped_lines_are_joined_but_lists_and_columns_stay_as_printed():
    from app.services.clause_outline import _joined

    text = ("BMO SB is a family of Multiple-\nAward contracts for\nagencies.\n\n(a) First item\nruns on.\n(b) Second item.\n\n"
            "   ●  Analyze spend data;\n   ●  Analyze the market;\n\nHVAC          Janitorial\nPlumbing      Pest Control")
    assert _joined(text) == ("BMO SB is a family of Multiple-Award contracts for agencies.\n\n(a) First item runs on.\n(b) Second item.\n\n"
                             "   ●  Analyze spend data;\n   ●  Analyze the market;\n\nHVAC          Janitorial\nPlumbing      Pest Control")


def test_a_document_without_sections_is_listed_in_checks_not_given_an_empty_sheet():
    letter = build_outline([(1, "Dear customer,\n\nThank you for your order.")])
    workbook = openpyxl.load_workbook(io.BytesIO(build_outline_xlsx([("bmo.pdf", build_outline(SOLICITATION)), ("letter.pdf", letter)])))
    assert workbook.sheetnames == ["Extracted Data", "Checks"]
    assert any(row[0] == "letter.pdf" and row[2] == "no sections" for row in workbook["Checks"].iter_rows(values_only=True))
