"""Drawn (vector) forms read box by box — app/source_structure/vector_forms.py.

Synthetic pages, built here, so each rule is tested on its own: caption over
value, merged boxes and boxes cut by a partial rule, several captions in one
box, a printed box left empty, text running across a divider, tick boxes
(and an unclear mark), and the negatives — a ruled table, a titled table,
prose set in columns — that must never be read as a form. Real documents
are covered in tests/test_source_regression.py.
"""

from __future__ import annotations

from uuid import uuid4

import fitz
from fastapi.testclient import TestClient

from app.database.session import SessionLocal
from app.main import app
from app.models.structure_record_review import StructureRecordReview
from app.source_structure.form_geometry import NOT_SELECTED, SELECTED, UNRECOGNIZED
from app.source_structure.pdf_structure import extract_page_structure, native_words

client = TestClient(app)

CAPTION, TYPED = 6, 9


def _box(page, rect, caption=None, value=None, value_at=None):
    page.draw_rect(fitz.Rect(*rect), color=(0, 0, 0), width=0.6)
    if caption:
        page.insert_text((rect[0] + 3, rect[1] + 8), caption, fontsize=CAPTION)
    if value:
        page.insert_text(value_at or (rect[0] + 3, rect[1] + 22), value, fontsize=TYPED)


def _tick(page, x, y, label, ticked=False):
    page.draw_rect(fitz.Rect(x, y, x + 7, y + 7), color=(0, 0, 0), width=0.5)
    if ticked:
        page.insert_text((x + 1.2, y + 6.5), "X", fontsize=8)
    page.insert_text((x + 10, y + 6), label, fontsize=CAPTION)


def _form(doc=None, unclear=False):
    doc = doc or fitz.open()
    page = doc.new_page()
    # A row of three boxes; the third printed but left empty.
    _box(page, (40, 50, 200, 90), "1. CONTRACT NO.", "W912-24-C-0001")
    _box(page, (200, 50, 360, 90), "2. DATE ISSUED", "01/15/2025")
    _box(page, (360, 50, 560, 90), "3. PROJECT NO.")
    # A merged box with a second caption in it, beside a column a partial
    # rule cuts in two.
    _box(page, (40, 90, 360, 150), "4. ISSUED BY", "CONTRACTING OFFICE")
    page.insert_text((250, 98), "CODE", fontsize=CAPTION)
    page.insert_text((280, 99), "N12345", fontsize=TYPED)
    page.insert_text((43, 125), "100 MAIN ST", fontsize=TYPED)
    _box(page, (360, 90, 560, 120), "5. TELEPHONE NO. (Include area code)", "(555) 123-4567")
    _box(page, (360, 120, 560, 150), "6. REMITTANCE ADDRESS", "See Item 4")
    # A numbered caption heading the lettered boxes in its row.
    _box(page, (40, 150, 140, 190), "7. FOR INFORMATION CALL:")
    _box(page, (140, 150, 360, 190), "A. NAME", "Jane Doe")
    _box(page, (360, 150, 560, 190), "B. EMAIL", "jane@example.gov")
    # Options in tick boxes.
    _box(page, (40, 190, 560, 230), "8. TYPE OF SOLICITATION")
    _tick(page, 60, 205, "SEALED BID", ticked=False)
    _tick(page, 200, 205, "NEGOTIATED", ticked=not unclear)
    if unclear:
        page.insert_text((150, 213), "X", fontsize=8)  # in no tick box
    # Two values set so close they run together across the divider.
    _box(page, (40, 230, 300, 270), "9. DATE SIGNED", "03/03/2025", value_at=(232, 252))
    _box(page, (300, 230, 560, 270), "10. AMOUNT", "$1,000.00", value_at=(303, 252))
    return doc


def _structure(doc, page_index=0):
    page = doc[page_index]
    return extract_page_structure(page_number=page_index + 1, words=native_words(page), extraction_method="native", fitz_page=page)


def _boxes(structure):
    return {
        (f.box_code, f.box_sub, f.label_text): f for f in structure.fields if f.structural_relation == "ruled_form_box"
    }


def test_each_box_is_its_printed_caption_over_its_value() -> None:
    fields = _boxes(_structure(_form()))
    assert fields[("1", None, "1. CONTRACT NO.")].raw_value == "W912-24-C-0001"
    assert fields[("2", None, "2. DATE ISSUED")].raw_value == "01/15/2025"
    # Printed, left empty: a blank value, accepted — not dropped.
    blank = fields[("3", None, "3. PROJECT NO.")]
    assert blank.raw_value == "" and blank.acceptance == "accepted"
    # Its position on the page is kept.
    assert fields[("1", None, "1. CONTRACT NO.")].box_rect == (40, 50, 200, 90)


def test_a_merged_box_and_a_box_cut_by_a_partial_rule() -> None:
    fields = _boxes(_structure(_form()))
    assert fields[("4", None, "4. ISSUED BY")].raw_value == "CONTRACTING OFFICE\n100 MAIN ST"
    assert fields[("5", None, "5. TELEPHONE NO. (Include area code)")].raw_value == "(555) 123-4567"
    assert fields[("6", None, "6. REMITTANCE ADDRESS")].raw_value == "See Item 4"


def test_a_second_caption_in_a_box_is_a_sub_field_of_its_item() -> None:
    code = _boxes(_structure(_form()))[("4", None, "CODE")]
    assert code.raw_value == "N12345" and code.box_caption == "ISSUED BY"


def test_lettered_boxes_are_sub_items_of_the_numbered_caption_in_their_row() -> None:
    fields = _boxes(_structure(_form()))
    name, email = fields[("7", "A", "NAME")], fields[("7", "B", "EMAIL")]
    assert (name.raw_value, name.box_caption) == ("Jane Doe", "FOR INFORMATION CALL:")
    assert email.raw_value == "jane@example.gov"
    # The caption itself is not repeated as an empty field.
    assert not [f for f in fields.values() if f.label_text.startswith("7. FOR INFORMATION")]


def test_text_running_across_a_divider_goes_to_the_box_each_word_is_in() -> None:
    fields = _boxes(_structure(_form()))
    assert fields[("9", None, "9. DATE SIGNED")].raw_value == "03/03/2025"
    assert fields[("10", None, "10. AMOUNT")].raw_value == "$1,000.00"


def test_tick_boxes_are_options_with_their_states() -> None:
    fields = _boxes(_structure(_form()))
    assert fields[("8", None, "SEALED BID")].box_choice == NOT_SELECTED
    assert fields[("8", None, "NEGOTIATED")].box_choice == SELECTED
    # The box holding only options isn't also an empty caption field.
    assert ("8", None, "8. TYPE OF SOLICITATION") not in fields


def test_a_mark_in_no_tick_box_is_unclear_and_assigned_to_no_option() -> None:
    fields = _boxes(_structure(_form(unclear=True)))
    assert fields[("8", None, "SEALED BID")].box_choice == UNRECOGNIZED
    assert fields[("8", None, "NEGOTIATED")].box_choice == UNRECOGNIZED


# --- never a form ------------------------------------------------------------------------------


def _ruled_table(page, top, title=None):
    columns, rows = [40, 120, 330, 420, 560], [["Item", "Description", "Qty", "Amount"]] + [
        [f"000{i}", f"Service line {i}", str(i * 2), f"${i * 1000:,}.00"] for i in range(1, 5)
    ]
    y = top
    if title:
        page.draw_rect(fitz.Rect(40, y, 560, y + 20), color=(0, 0, 0), width=0.6)
        page.insert_text((44, y + 13), title, fontsize=9)
        y += 20
    for r, cells in enumerate(rows):
        for c, text in enumerate(cells):
            page.draw_rect(fitz.Rect(columns[c], y, columns[c + 1], y + 18), color=(0, 0, 0), width=0.6)
            page.insert_text((columns[c] + 3, y + 12), text, fontsize=9)
        y += 18


def test_a_ruled_table_is_a_table_not_form_boxes() -> None:
    doc = fitz.open()
    _ruled_table(doc.new_page(), 60)
    structure = _structure(doc)
    assert not _boxes(structure)
    table = next(t for t in structure.tables if t.acceptance == "accepted")
    assert table.headers == ["Item", "Description", "Qty", "Amount"] and len(table.rows) == 4


def test_a_titled_ruled_table_is_not_a_form() -> None:
    """A title row over a grid splits differently from its body, like a
    form's rows do; with no numbered captions it is still a table."""

    doc = fitz.open()
    _ruled_table(doc.new_page(), 60, title="Schedule of Prices")
    structure = _structure(doc)
    assert not _boxes(structure)
    table = next(t for t in structure.tables if t.acceptance == "accepted")
    # The title is the table's caption; the row of labels its header.
    assert table.caption == "Schedule of Prices" and table.headers == ["Item", "Description", "Qty", "Amount"]


def test_prose_set_in_columns_is_not_a_table_but_aligned_figures_are() -> None:
    doc = fitz.open()
    page = doc.new_page()
    prose = [
        "The agencies have determined that this", "rule implements the trade agreement", "thresholds published by the",
        "office and applies to acquisitions", "made after the effective date of", "the notice, and does not change",
        "the procedures for evaluating offers", "under the agreements, which remain", "in effect for every solicitation",
    ]
    for line in range(9):
        for col, x in enumerate((40, 220, 400)):
            page.insert_text((x, 80 + line * 12), prose[(line + col * 3) % 9], fontsize=8)
    figures = [("WTO GPA", "174,000", "6,683,000"), ("Chile FTA", "105,767", "6,683,000"),
               ("Korea FTA", "100,000", "6,683,000"), ("Oman FTA", "174,000", "13,749,689")]
    for row, cells in enumerate(figures):
        for col, x in enumerate((40, 300, 450)):
            page.insert_text((x, 300 + row * 14), cells[col], fontsize=9)
    structure = _structure(doc)
    accepted = [t for t in structure.tables if t.acceptance == "accepted"]
    assert not any("agencies" in c.text for t in accepted for r in t.rows for c in r)
    assert any(any(c.text == "Chile FTA" for r in t.rows for c in r) for t in accepted)


# --- through the layout ----------------------------------------------------------------------------


def _upload(doc) -> str:
    response = client.post("/api/documents/upload", files={"file": (f"form-{uuid4().hex[:6]}.pdf", doc.tobytes(), "application/pdf")})
    assert response.status_code == 201, response.text
    document_id = response.json()["document_id"]
    assert client.post(f"/api/documents/{document_id}/extract-pages", json={"run_ocr": False}).status_code == 200
    return document_id


def _layout_fields(document_id):
    layout = client.get(f"/api/documents/{document_id}/original-structure").json()
    return layout, [i for s in layout["sections"] for i in s["items"] if i["kind"] == "field"]


def test_the_layout_shows_numbers_sub_items_and_choices_and_flags_an_unclear_mark() -> None:
    _, fields = _layout_fields(_upload(_form()))
    by_name = {f["field_name"]: f for f in fields}
    assert by_name["CONTRACT NO."]["item"]["number"] == "1"
    assert by_name["NAME"]["item"]["name"] == "FOR INFORMATION CALL:" and by_name["NAME"]["sub_item"] == "A"
    assert by_name["NEGOTIATED"]["choice"] == "Selected" and by_name["SEALED BID"]["choice"] == "Not Selected"
    _, unclear = _layout_fields(_upload(_form(unclear=True)))
    flagged = {f["field_name"]: [x["code"] for x in f["flags"]] for f in unclear}
    assert "unclear_mark" in flagged["NEGOTIATED"] and "unclear_mark" in flagged["SEALED BID"]


def test_a_review_under_an_old_key_stays_with_its_field_or_is_listed() -> None:
    """A review saved before the field's label was read differently: it
    follows the one field on its page holding exactly the value it
    reviewed; one that fits no single field is listed, never dropped."""

    document_id = _upload(_form())
    database = SessionLocal()
    try:
        database.add_all([
            StructureRecordReview(document_id=document_id, record_key="field:1::contract-number-old:0", record_kind="field",
                                  status="approved", original_value="W912-24-C-0001", history=[]),
            StructureRecordReview(document_id=document_id, record_key="field:1::gone:0", record_kind="field",
                                  status="approved", original_value="no such value", history=[]),
        ])
        database.commit()
    finally:
        database.close()
    layout, fields = _layout_fields(document_id)
    contract = next(f for f in fields if f["field_name"] == "CONTRACT NO.")
    assert contract["review_status"] == "approved"
    assert [r["record_key"] for r in layout["unattached_reviews"]] == ["field:1::gone:0"]
