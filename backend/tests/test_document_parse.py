"""Parse API (api/document_parse.py, source_structure/parse_view.py): a
document's complete content as typed, source-located blocks, read only.

A small synthetic contract checks the contract itself (labels, paging,
completeness, no writes, masking, isolation); the regression documents
(tests/fixtures/source_regression.py) check it on real content."""

from __future__ import annotations

import csv
import io
import re
import secrets
import time
from collections import Counter
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select

from app.core.auth import ActorContext, get_current_actor
from app.core.config import get_settings
from app.database.session import SessionLocal
from app.main import app
from app.models.document_source_structure import DocumentSourceStructure
from app.source_structure.parse_export import Row, build_parse_csv, build_parse_xlsx
from tests.fixtures.source_regression import DOCS, REGRESSION

client = TestClient(app)
DOC_BY_KEY = {doc.key: doc for doc in DOCS}
GSA_CONTRACT = REGRESSION / "Contract_47QRCA25DSF07 (2).pdf"


@contextmanager
def enforced():
    settings = get_settings().model_copy(update={"rbac_enforced": True, "public_workspace_access": True})
    with patch("app.core.auth.get_settings", return_value=settings):
        yield


@contextmanager
def as_role(role: str):
    app.dependency_overrides[get_current_actor] = lambda: ActorContext(id=f"t-{role}", actor_type="user", role=role, display_name=role)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_actor, None)


def _contract_pdf(pages: int = 4) -> bytes:
    pdf = fitz.open()
    for number in range(1, pages + 1):
        page = pdf.new_page(width=612, height=792)
        page.insert_text((72, 40), "ACME SUPPLY CONTRACT W91ZZZ-26-C-0042", fontsize=9)
        page.insert_text((72, 110), f"Section {number}. Terms", fontsize=14)
        page.insert_text((72, 140), f"(a) The Contractor shall deliver item {number} by the stated date.", fontsize=10)
        page.insert_text((72, 156), "(b) Payments go to account 123456789012 for employee 123-45-6789.", fontsize=10)
        page.insert_text((72, 190), "(End of clause)", fontsize=10)
        page.insert_text((280, 770), f"Page {number} of {pages}", fontsize=9)
    return pdf.tobytes()


_UPLOADED: list[tuple[str, dict]] = []


@pytest.fixture(scope="module", autouse=True)
def _remove_uploads():
    """The regression files are uploaded again by other suites: leave no
    duplicate of them behind."""

    yield
    with patch("app.services.document_deletion.delete_object"):
        for document_id, headers in _UPLOADED:
            client.delete(f"/api/documents/{document_id}", headers=headers)


def _upload(content: bytes, name: str, kind: str = "application/pdf", headers: dict | None = None, *, ocr: bool = False) -> str:
    response = client.post("/api/documents/upload", files={"file": (name, content, kind)}, headers=headers or {})
    assert response.status_code == 201, response.text
    document_id = response.json()["document_id"]
    _UPLOADED.append((document_id, headers or {}))
    extracted = client.post(f"/api/documents/{document_id}/extract-pages", json={"run_ocr": ocr}, headers=headers or {})
    assert extracted.status_code == 200, extracted.text
    return document_id


def _build_structure(document_id: str) -> None:
    """The normal path that stores a document's source structure (what the
    workspace triggers on first open) — Parse itself never does this."""

    assert client.get(f"/api/documents/{document_id}/source-structure").status_code == 200


def _all_pages(document_id: str, page_limit: int = 25) -> tuple[list[dict], list[dict], list[float]]:
    pages, responses, seconds = [], [], []
    start: int | None = 1
    while start is not None:
        began = time.perf_counter()
        response = client.get(f"/api/documents/{document_id}/parse", params={"start_page": start, "page_limit": page_limit})
        seconds.append(time.perf_counter() - began)
        assert response.status_code == 200, response.text
        body = response.json()
        responses.append(body)
        pages.extend(body["pages"])
        start = body["window"]["next_start_page"]
    return pages, responses, seconds


@pytest.fixture(scope="module")
def contract() -> str:
    document_id = _upload(_contract_pdf(), f"parse-{uuid4().hex[:6]}.pdf")
    _build_structure(document_id)
    return document_id


# --- the contract ---------------------------------------------------------------------------


def test_identity_window_and_run(contract):
    body = client.get(f"/api/documents/{contract}/parse").json()
    assert body["parse_version"] == 1
    assert body["document"]["id"] == contract and body["document"]["page_count"] == 4
    assert body["document"]["checksum_sha256"] == body["run"]["checksum_sha256"]
    assert body["run"]["structure"]["status"] == "current"
    assert body["window"] == {"start_page": 1, "end_page": 4, "page_limit": 10, "next_start_page": None, "total_pages": 4}
    assert [page["page_number"] for page in body["pages"]] == [1, 2, 3, 4]
    # No file path or URL to the stored original is handed out.
    assert "stored_filename" not in str(body) and "file://" not in str(body)


def test_blocks_are_typed_ordered_and_located(contract):
    page = client.get(f"/api/documents/{contract}/parse").json()["pages"][1]
    types = [block["type"] for block in page["blocks"]]
    assert types[0] == "header" and types[-1] == "page_reference"
    assert "heading" in types and "marginalia" in types and "paragraph" in types
    texts = [block["text"] for block in page["blocks"]]
    assert texts[types.index("marginalia")] == "(End of clause)"
    # Labels are additive: the reading-order kind is kept, the text untouched.
    header = page["blocks"][0]
    assert header["source_kind"] in {"paragraph", "heading"} and header["text"] == "ACME SUPPLY CONTRACT W91ZZZ-26-C-0042"
    # Reading order is the order of the list; ids are page-scoped and stable.
    assert [block["index"] for block in page["blocks"]] == list(range(len(page["blocks"])))
    assert all(block["id"] == f"p2.b{block['index']}" for block in page["blocks"])
    # Every block on a positioned page has a real box inside the page.
    for block in page["blocks"]:
        x0, y0, x1, y1 = block["bbox"]
        assert 0 <= x0 < x1 <= page["width"] and 0 <= y0 < y1 <= page["height"]
        assert block["locator"] is None
    # Paragraph labels are kept exactly as printed.
    assert any(text.startswith("(a) The Contractor shall deliver item 2") for text in texts)


def test_every_source_word_is_in_a_block(contract):
    for page in client.get(f"/api/documents/{contract}/parse").json()["pages"]:
        assert page["positioning"] == "spatial"
        assert page["completeness"]["missing_characters"] == 0 and page["completeness"]["complete"]
        assert page["completeness"]["source_characters"] == page["completeness"]["block_characters"]


def test_paging_is_stable_and_loses_nothing(contract):
    whole = client.get(f"/api/documents/{contract}/parse").json()
    first = client.get(f"/api/documents/{contract}/parse", params={"page_limit": 3}).json()
    assert first["window"]["next_start_page"] == 4 and first["window"]["end_page"] == 3
    rest = client.get(f"/api/documents/{contract}/parse", params={"start_page": 4, "page_limit": 3}).json()
    assert rest["window"]["next_start_page"] is None
    ids = [b["id"] for p in first["pages"] + rest["pages"] for b in p["blocks"]]
    assert ids == [b["id"] for p in whole["pages"] for b in p["blocks"]]
    again = client.get(f"/api/documents/{contract}/parse", params={"page_limit": 3}).json()
    assert again["pages"] == first["pages"]


def test_limits_and_unknown_documents(contract):
    assert client.get(f"/api/documents/{contract}/parse", params={"page_limit": 26}).status_code == 422
    assert client.get(f"/api/documents/{contract}/parse", params={"start_page": 0}).status_code == 422
    assert client.get(f"/api/documents/{uuid4()}/parse").status_code == 404
    past = client.get(f"/api/documents/{contract}/parse", params={"start_page": 9}).json()
    assert past["pages"] == [] and past["window"]["next_start_page"] is None


def test_a_get_never_extracts_or_writes(contract):
    database = SessionLocal()
    try:
        before = database.scalars(select(DocumentSourceStructure).where(DocumentSourceStructure.document_id == contract)).one()
        stamp = (before.extractor_version, dict(before.payload_json))
    finally:
        database.close()
    refuse = AssertionError("Parse must not extract")
    with patch("app.source_structure.service.build_source_structure", side_effect=refuse), \
         patch("app.source_structure.service.build_and_persist_source_structure", side_effect=refuse), \
         patch("app.recognition.page_ocr.PageOcrEngine.__init__", side_effect=refuse), \
         patch("fitz.Page.get_textpage_ocr", side_effect=refuse), \
         patch("sqlalchemy.orm.Session.commit", side_effect=AssertionError("Parse must not write")):
        assert client.get(f"/api/documents/{contract}/parse").status_code == 200
    database = SessionLocal()
    try:
        after = database.scalars(select(DocumentSourceStructure).where(DocumentSourceStructure.document_id == contract)).one()
        assert (after.extractor_version, dict(after.payload_json)) == stamp
    finally:
        database.close()


def test_a_missing_structure_is_reported_not_rebuilt():
    document_id = _upload(_contract_pdf(2), f"parse-nostructure-{uuid4().hex[:6]}.pdf")
    body = client.get(f"/api/documents/{document_id}/parse").json()
    assert body["run"]["structure"]["status"] == "missing"
    assert any("No source structure is stored" in warning for warning in body["warnings"])
    # The page text is all still there; form fields are unavailable (null), not "none" ([]).
    assert all(page["completeness"]["complete"] and page["elements"] is None for page in body["pages"])
    database = SessionLocal()
    try:
        assert database.scalars(select(DocumentSourceStructure).where(DocumentSourceStructure.document_id == document_id)).first() is None
    finally:
        database.close()


def test_callers_who_cannot_export_see_identifiers_masked(contract):
    plain = client.get(f"/api/documents/{contract}/parse").json()
    assert plain["masking"]["applied"] is False
    assert "123-45-6789" in str(plain["pages"]) and "123456789012" in str(plain["pages"])
    with as_role("viewer"):
        masked = client.get(f"/api/documents/{contract}/parse").json()
    assert masked["masking"]["applied"] is True
    pages = str(masked["pages"])
    assert "123-45-6789" not in pages and "123456789012" not in pages
    assert "*****6789" in pages and "*****9012" in pages
    # Masking changes identifier shapes only, never the rest of the text or the boxes.
    for a, b in zip(plain["pages"][0]["blocks"], masked["pages"][0]["blocks"]):
        assert a["bbox"] == b["bbox"] and a["type"] == b["type"]
    for role in ("analyst", "reviewer", "admin"):
        with as_role(role):
            assert client.get(f"/api/documents/{contract}/parse").json()["masking"]["applied"] is False


def test_another_workspace_cannot_read_a_document():
    a = {"X-Workspace-Token": secrets.token_hex(32)}
    b = {"X-Workspace-Token": secrets.token_hex(32)}
    with enforced():
        mine = _upload(_contract_pdf(1), f"parse-ws-{uuid4().hex[:6]}.pdf", headers=a)
        assert client.get(f"/api/documents/{mine}/parse", headers=a).status_code == 200
        assert client.get(f"/api/documents/{mine}/parse", headers=b).status_code == 404
        assert client.get(f"/api/documents/{mine}/parse").status_code == 404


# --- regression documents ---------------------------------------------------------------------


def _regression_upload(key: str) -> str:
    doc = DOC_BY_KEY[key]
    if not (REGRESSION / doc.file).exists():
        pytest.skip(f"{doc.file} not available locally")
    raw = (REGRESSION / doc.file).read_bytes()
    if doc.file.endswith(".html"):
        document_id = _upload(raw, f"{key}-{uuid4().hex[:6]}.html", "text/html")
    else:
        if doc.pages:
            src = fitz.open(stream=raw, filetype="pdf")
            part = fitz.open()
            part.insert_pdf(src, from_page=0, to_page=min(doc.pages, src.page_count) - 1)
            raw = part.tobytes()
        document_id = _upload(raw, f"{key}-{uuid4().hex[:6]}.pdf", ocr=True)
    _build_structure(document_id)
    return document_id


def test_sf33_form_boxes_are_elements_of_their_blocks():
    document_id = _regression_upload("SF33_FA30")
    pages, _, seconds = _all_pages(document_id)
    elements = [element for page in pages for element in page["elements"] or []]
    print(f"\nSF33 FA30: {len(pages)} pages, {sum(len(p['blocks']) for p in pages)} blocks, {len(elements)} elements, "
          f"window seconds {[round(s, 2) for s in seconds]}")
    codes = {str(element["item_number"]).rstrip(".") for element in elements if element["item_number"]}
    # SF33 numbered boxes as printed (2 contract no., 3 solicitation no., 5 date issued, …).
    assert {"2", "3", "5"} <= codes, codes
    # The printed value, what extraction read and the reviewed value are kept apart.
    assert all({"printed_value", "extracted_value", "reviewed_value"} <= set(element) for element in elements)
    assert any(element["type"] == "checkbox" and element["choice"] for element in elements)
    linked = [element for element in elements if element["block_id"]]
    assert len(linked) >= 0.8 * len(elements), (len(linked), len(elements))
    block_ids = {block["id"] for page in pages for block in page["blocks"]}
    assert all(element["block_id"] in block_ids for element in linked)
    assert all(page["completeness"]["complete"] for page in pages if page["positioning"] == "spatial"), [
        (page["page_number"], page["completeness"]) for page in pages if not page["completeness"]["complete"]
    ]


def test_far_part_52_html_keeps_its_order_says_page_only_and_matches_the_outline():
    document_id = _regression_upload("FAR52_html")
    pages, responses, seconds = _all_pages(document_id)
    blocks = [block for page in pages for block in page["blocks"]]
    print(f"\nFAR part 52 (HTML): {len(pages)} pages, {len(blocks)} blocks, "
          f"{sum(b['type'] == 'marginalia' for b in blocks)} marginalia, {responses[0]['sections']['total']} outline rows, "
          f"window seconds {[round(s, 2) for s in seconds]}")
    assert blocks and all(block["bbox"] is None and "HTML has no page coordinates" in block["locator"] for block in blocks)
    assert sum(block["type"] == "marginalia" for block in blocks) > 100
    sections = responses[0]["sections"]
    outline = client.get(f"/api/documents/{document_id}/clause-outline").json()
    assert sections["status"] == "available" and sections["style"] == outline["style"]
    shown = sum(len(r["sections"]["rows"]) for r in responses)
    assert shown == sections["total"] == sum(1 for record in outline["records"] if record["kind"] in {"section", "clause", "paragraph"})
    assert all(page["completeness"]["complete"] for page in pages)


def test_gsa_contract_all_92_pages_are_retrievable_and_complete():
    if not GSA_CONTRACT.exists():
        pytest.skip("GSA contract not available locally")
    document_id = _upload(GSA_CONTRACT.read_bytes(), f"gsa-{uuid4().hex[:6]}.pdf")
    _build_structure(document_id)
    pages, responses, seconds = _all_pages(document_id, page_limit=25)
    assert [page["page_number"] for page in pages] == list(range(1, 93))
    assert responses[0]["document"]["page_count"] == 92 and len(responses) == 4
    totals = Counter()
    for page in pages:
        totals["source"] += page["completeness"]["source_characters"]
        totals["blocks"] += page["completeness"]["block_characters"]
        totals["missing"] += page["completeness"]["missing_characters"]
        totals["tables_with_cell_gaps"] += page["completeness"]["tables_with_cell_gaps"]
    incomplete = [(page["page_number"], page["completeness"]["missing_tokens"]) for page in pages if not page["completeness"]["complete"]]
    print(f"\nGSA 92 pages: {sum(len(p['blocks']) for p in pages)} blocks, tokens {dict(totals)}, "
          f"incomplete pages {incomplete}, window seconds {[round(s, 2) for s in seconds]}")
    assert totals["missing"] == 0, incomplete
    # The clause GSAR 552.242-99 reads verbatim with its paragraph labels.
    text = "\n".join(block["text"] for page in pages for block in page["blocks"])
    assert re.search(r"GSAR 552\.242-99 Cancellation \(Non-Schedules\) \(Apr 2023\)", text)
    assert "Either party may cancel this contract in whole or in part by providing written notice." in text
    # Large documents stay responsive: no 25-page window takes longer than this.
    assert max(seconds) < 20, seconds


def test_a_printed_page_reference_is_labelled_wherever_it_sits():
    from app.source_structure.parse_view import _label

    # "Page 1 of 154" printed above the bottom margin (a solicitation's footer line).
    assert _label("paragraph", "Page 1 of 154", [518, 657, 578, 672], 792, set()) == "page_reference"
    # A bare number is a page number only in a margin; mid-page it is text.
    assert _label("paragraph", "12", [300, 400, 310, 410], 792, set()) == "paragraph"
    assert _label("paragraph", "12", [300, 770, 310, 780], 792, set()) == "page_reference"


# --- the download ---------------------------------------------------------------------------


def _csv_rows(document_id: str) -> list[list[str]]:
    response = client.get(f"/api/documents/{document_id}/parse/export.csv")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "parsed.csv" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_csv_download_keeps_the_pages_order_and_every_line(contract):
    rows = _csv_rows(contract)
    assert rows[0][:4] == ["Page", "Block", "Type", "Content 1"]
    body = rows[1:]
    assert [int(row[0]) for row in body] == sorted(int(row[0]) for row in body)
    assert {row[0] for row in body} == {"1", "2", "3", "4"}
    # Blocks are counted through the document, and each printed line has its own row.
    numbers = [int(row[1]) for row in body]
    assert numbers == sorted(numbers) and numbers[0] == 1
    assert ["Section 2. Terms"] in [row[3:] for row in body if row[0] == "2"]
    assert any(row[2] == "Marginalia" and row[3] == "(End of clause)" for row in body)
    assert any(row[2] == "Page number" and row[3] == "Page 4 of 4" for row in body)


def test_excel_download_holds_the_same_content_as_the_csv(contract):
    response = client.get(f"/api/documents/{contract}/parse/export.xlsx")
    assert response.status_code == 200, response.text
    assert "parsed.xlsx" in response.headers["content-disposition"]
    sheet = load_workbook(io.BytesIO(response.content)).active
    cells = list(sheet.iter_rows(values_only=True))
    assert cells[0][:3] == ("Page", "Block", "Type")
    assert [row[0] for row in cells if isinstance(row[0], str) and row[0].startswith("Page ")] == ["Page 1", "Page 2", "Page 3", "Page 4"]
    excel_lines = [row[3] for row in cells[1:] if row[3]]
    assert excel_lines == [row[3] for row in _csv_rows(contract)[1:]]


def test_download_writes_tables_as_cells_and_never_runs_formulas():
    rows = [
        Row(1, 1, "Text", ["=HYPERLINK(\"http://x\")"]),
        Row(1, 2, "Text", ["- Logistics"]),
        Row(1, 3, "Table", ["CLIN", "Amount"], "table_header"),
        Row(1, 3, "Table", ["0001", "-5.00"], "table_cell"),
    ]
    parsed = list(csv.reader(io.StringIO(build_parse_csv(rows))))
    assert parsed[1][3] == "'=HYPERLINK(\"http://x\")"
    assert parsed[2][3] == "'- Logistics"
    assert parsed[4][3:] == ["0001", "-5.00"]
    sheet = load_workbook(io.BytesIO(build_parse_xlsx(rows, "a.pdf"))).active
    values = {cell.value: cell.data_type for row in sheet.iter_rows() for cell in row if cell.value is not None}
    assert values["=HYPERLINK(\"http://x\")"] == "s"
    assert values["0001"] == "s" and values["-5.00"] == "s"


def test_download_needs_export_permission(contract):
    with enforced(), as_role("viewer"):
        assert client.get(f"/api/documents/{contract}/parse").status_code == 200
        assert client.get(f"/api/documents/{contract}/parse/export.csv").status_code == 403
        assert client.get(f"/api/documents/{contract}/parse/export.xlsx").status_code == 403


def test_download_of_an_unknown_document_is_not_found():
    assert client.get(f"/api/documents/{uuid4()}/parse/export.csv").status_code == 404
