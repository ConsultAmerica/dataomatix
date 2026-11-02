"""Increment 7.3.4 regression: real documents against their own printed
content (tests/fixtures/source_regression.py).

Each document runs the production path once (upload, page extraction with
OCR fallback, Original File layout, Excel export), then every expectation is
checked on what the screen shows (the layout without its hidden form
re-readings) and on the workbook. An expectation not yet met is marked
xfail(strict) with the step expected to fix it: when that step lands the
test passes, strict xfail turns it red, and its marker is removed.
"""

from __future__ import annotations

import io
import re
from uuid import uuid4

import fitz
import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.database.session import SessionLocal
from app.main import app
from app.models.document import Document
from app.source_structure.original_export import build_original_structure_xlsx
from app.staging.custom_export import safe_cell
from app.source_structure.original_layout import original_layout_for
from tests.fixtures.source_regression import DOCS, REGRESSION, REQUIRED_COVERAGE, Doc

client = TestClient(app)
DOC_BY_KEY = {doc.key: doc for doc in DOCS}
GENERIC_HEADER = re.compile(r"^Column \d+$")
PRINTED_NUMBER = re.compile(r"^\s*(\d{1,3}(?:\s?[A-Za-z])?)[.)]?\s+\S")


def _norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _key(text: object) -> str:
    """Comparison form: case, spacing and trailing punctuation ignored."""
    return _norm(text).casefold().rstrip(".:")


def _cell(cell: object) -> str:
    return _norm(cell.get("text") if isinstance(cell, dict) else cell)


_built: dict[str, dict] = {}


def _source_bytes(doc: Doc) -> tuple[bytes, str]:
    raw = (REGRESSION / doc.file).read_bytes()
    if doc.file.endswith(".html"):
        return raw, "text/html"
    if doc.pages:
        src = fitz.open(stream=raw, filetype="pdf")
        part = fitz.open()
        part.insert_pdf(src, from_page=0, to_page=min(doc.pages, src.page_count) - 1)
        raw = part.tobytes()
    return raw, "application/pdf"


def built(key: str) -> dict:
    """The document's layout, workbook rows and visible items, built once."""

    if key in _built:
        return _built[key]
    doc = DOC_BY_KEY[key]
    if not (REGRESSION / doc.file).exists():
        pytest.skip(f"{doc.file} not available locally")
    raw, mime = _source_bytes(doc)
    suffix = ".html" if mime == "text/html" else ".pdf"
    response = client.post("/api/documents/upload", files={"file": (f"{key}-{uuid4().hex[:6]}{suffix}", raw, mime)})
    assert response.status_code == 201, response.text
    document_id = response.json()["document_id"]
    assert client.post(f"/api/documents/{document_id}/extract-pages", json={"run_ocr": True}).status_code == 200
    database = SessionLocal()
    try:
        layout = original_layout_for(database, database.get(Document, document_id))
    finally:
        database.close()
    workbook = openpyxl.load_workbook(io.BytesIO(build_original_structure_xlsx(layout)), read_only=True)
    sheet_rows = [tuple(_norm(v) for v in row) for ws in workbook.worksheets for row in ws.iter_rows(values_only=True)]
    shown = [(section, item) for section in layout["sections"] for item in section["items"] if not item.get("form_duplicate")]
    _built[key] = {
        "layout": layout,
        "rows": sheet_rows,
        "fields": [(s, i) for s, i in shown if i["kind"] == "field"],
        "tables": [(s, i) for s, i in shown if i["kind"] == "table"],
        "is_html": mime == "text/html",
    }
    return _built[key]


def _marks(fix: int | None) -> list:
    return [pytest.mark.xfail(strict=True, reason=f"baseline failure; 7.3.4 step {fix}")] if fix else []


def _cases(kind: str):
    for doc in DOCS:
        for index, expected in enumerate(getattr(doc, kind)):
            label = getattr(expected, "name", None) or getattr(expected, "option", None) or getattr(expected, "text", None) \
                or getattr(expected, "pattern", None) or " | ".join(getattr(expected, "headers", ())[:2])
            yield pytest.param(doc.key, expected, id=f"{doc.key}-{index}-{_norm(label)[:30]}", marks=_marks(expected.fix))


# --- fields ------------------------------------------------------------------


def _item_number(field: dict) -> str:
    return _key((field.get("item") or {}).get("number")).rstrip(".")


def _field_matches(field: dict, expected) -> bool:
    if expected.page is not None and field.get("page") != expected.page:
        return False
    if _item_number(field) != _key(expected.item):
        return False
    names = {_key(field.get("field_name")), _key(field.get("label"))}
    if _key(expected.name) not in names:
        return False
    if expected.parent is not None:
        if _key((field.get("item") or {}).get("name")) != _key(expected.parent):
            return False
        if expected.sub is not None and _key(field.get("sub_item")) != _key(expected.sub):
            return False
    value = _norm(field.get("extracted_value"))
    parts = " ".join(_norm(p.get("value")) for p in field.get("parts") or [])
    if expected.contains:
        return _key(expected.value) in _key(value) or _key(expected.value) in _key(parts)
    return _key(value) == _key(expected.value)


@pytest.mark.parametrize(("key", "expected"), list(_cases("fields")))
def test_printed_field(key, expected) -> None:
    """The box is extracted with its printed number, printed name (and
    parent caption / sub-item letter) and its value; a blank box stays blank."""

    data = built(key)
    hits = [f for _, f in data["fields"] if _field_matches(f, expected)]
    assert len(hits) == 1, (
        f"expected item {expected.item} {expected.name!r} = {expected.value!r} once; found {len(hits)}. "
        f"Fields with that number: {[(f.get('field_name'), f.get('extracted_value')) for _, f in data['fields'] if _item_number(f) == _key(expected.item)][:6]}"
    )


@pytest.mark.parametrize(("key", "expected"), list(_cases("choices")))
def test_selection_box(key, expected) -> None:
    """A selection box keeps its printed option label and a definite state."""

    data = built(key)
    hits = [
        f for _, f in data["fields"]
        # "12A" printed as one box or as item 12, sub-item A: either matches.
        if f.get("page") == expected.page
        and _key(expected.item) in {_item_number(f), _item_number(f) + _key(f.get("sub_item"))}
        and _key(expected.option) in {_key(f.get("field_name")), _key(f.get("label"))}
    ]
    # Shown on screen and in Excel under its full printed option label.
    if hits:
        assert _key(hits[0].get("field_name") or hits[0].get("label")) == _key(expected.option)
    assert len(hits) == 1, f"option {expected.option!r} of item {expected.item}: {len(hits)} fields"
    assert _norm(hits[0].get("choice")) == expected.state


@pytest.mark.parametrize(("key", "expected"), list(_cases("no_loose_fields")))
def test_no_loose_field(key, expected) -> None:
    data = built(key)
    pattern = re.compile(expected.pattern, re.I)
    offending = [
        f for _, f in data["fields"]
        if any(pattern.search(f"{tag}: {_norm(f.get(attr))}") for tag, attr in
               (("label", "label"), ("name", "field_name"), ("value", "extracted_value")))
    ]
    assert not offending, f"{expected.reason}: {[(f.get('label'), f.get('extracted_value')) for f in offending[:5]]}"


# --- tables ------------------------------------------------------------------


def _table_headers(table: dict) -> list[str]:
    return [_norm(h) for h in table.get("headers") or []]


@pytest.mark.parametrize(("key", "expected"), list(_cases("tables")))
def test_genuine_table(key, expected) -> None:
    """The table is found with its printed headers, its rows and its cells."""

    data = built(key)
    want = [_key(h) for h in expected.headers]
    candidates = [
        t for _, t in data["tables"]
        if (expected.page is None or expected.page in (t.get("pages") or []))
        and [_key(h) for h in _table_headers(t)][: len(want)] == want
        and (expected.title is None or _key(expected.title) in _key(t.get("title")))
    ]
    assert candidates, (
        f"no table with headers {list(expected.headers)} on page {expected.page}; tables there: "
        f"{[_table_headers(t)[:6] for _, t in data['tables'] if expected.page is None or expected.page in (t.get('pages') or [])]}"
    )
    table = candidates[0]
    rows = [[_cell(c) for c in r["cells"]] + [_norm(a) for a in (r.get("attributes") or {}).values()] for r in table["rows"]]
    if expected.row_count is not None:
        assert table["row_count"] == expected.row_count
    for first, values in expected.rows.items():
        # A row is found by its key: its first cell's text, or a whole cell
        # (a table of contents' "SEC." column after its "(X)" mark).
        row = next((r for r in rows if r and (_key(r[0]).startswith(_key(first)) or _key(first) in {_key(c) for c in r})), None)
        assert row is not None, f"no row keyed {first!r}"
        text = " | ".join(row)
        missing = [v for v in values if v not in text]
        assert not missing, f"row {first!r} lacks {missing}: {text[:200]}"


@pytest.mark.parametrize(("key", "expected"), list(_cases("not_tables")))
def test_not_a_table(key, expected) -> None:
    data = built(key)
    offending = [
        t for _, t in data["tables"]
        if (expected.page is None or expected.page in (t.get("pages") or []))
        and any(expected.text in _cell(c) for r in t["rows"] for c in r["cells"])
    ]
    assert not offending, f"{expected.kind} read as a table: headers {_table_headers(offending[0])}"


# --- every document ------------------------------------------------------------

ALL = [doc.key for doc in DOCS]
_GENERIC_FIX = {"FAR52_html": 7}
_DUPLICATE_FIX = {"SF33_FA30": 5, "SF33_47QRC": 5}


def _per_doc(fixes: dict[str, int]):
    return [pytest.param(key, id=key, marks=_marks(fixes.get(key))) for key in ALL]


@pytest.mark.parametrize("key", _per_doc(_GENERIC_FIX))
def test_no_invented_headers(key) -> None:
    """A table without a printed header row keeps its columns but never
    presents generated "Column N" labels as printed headers (screen or Excel)."""

    data = built(key)
    invented = [_table_headers(t) for _, t in data["tables"] if any(GENERIC_HEADER.match(h) for h in _table_headers(t))]
    assert not invented, f"{len(invented)} table(s) with invented headers, e.g. {invented[0][:4]}"
    assert not any(GENERIC_HEADER.match(v) for row in data["rows"] for v in row if v)


@pytest.mark.parametrize("key", _per_doc({"SF33_FA30": 4}))
def test_printed_numbering_preserved(key) -> None:
    """A field whose printed label starts with a number shows that number."""

    data = built(key)
    wrong = []
    for _, f in data["fields"]:
        if f.get("found_by") == "ruled form box" and (f.get("item") or {}).get("has_subfields"):
            continue  # an option's own words in a box ("10 U.S.C. 2304(c)") aren't its item's number
        match = PRINTED_NUMBER.match(_norm(f.get("label")))
        printed = match.group(1).replace(" ", "").casefold() if match else None
        if match and (f.get("item") or {}).get("number") and _item_number(f) != printed:
            wrong.append((f["label"][:40], f["item"]["number"]))
    assert not wrong, wrong[:5]


@pytest.mark.parametrize("key", _per_doc(_DUPLICATE_FIX))
def test_no_duplicate_records(key) -> None:
    """No field (same section, label and value) or table (same section,
    headers and rows) is extracted twice."""

    data = built(key)
    seen: dict[tuple, int] = {}
    for section, f in data["fields"]:
        if _norm(f.get("extracted_value")):
            k = (section["id"], _key(f.get("label")), _key(f.get("extracted_value")))
            seen[k] = seen.get(k, 0) + 1
    tables: dict[tuple, int] = {}
    for section, t in data["tables"]:
        # One printed table read twice is a duplicate; two printed alike (a
        # clause's blank lists for different end products) are not.
        k = (section["id"], tuple(sorted(t.get("source_tables") or [])), tuple(_table_headers(t)),
             tuple(tuple(_cell(c) for c in r["cells"]) for r in t["rows"]))
        tables[k] = tables.get(k, 0) + 1
    assert not [k for k, n in seen.items() if n > 1], [k[1:] for k, n in seen.items() if n > 1][:5]
    assert not [k for k, n in tables.items() if n > 1]


@pytest.mark.parametrize("key", _per_doc({}))
def test_screen_and_excel_hold_the_same_data(key) -> None:
    """Every field shown on screen is in the workbook with its item number,
    name and value (or its parts); every table header and cell too."""

    data = built(key)
    rows = data["rows"]
    # The workbook writes text that could run as a formula escaped.
    excel = lambda v: _norm(safe_cell(v)) if v else v
    by_value: dict[str, list[tuple]] = {}
    for row in rows:
        for v in row:
            if v:
                by_value.setdefault(v, []).append(row)
    missing = []
    for _, f in data["fields"]:
        name = _norm(f.get("field_name") or f.get("label"))
        # As the screen shows it: a choice box by its state (shownValue).
        shown = f.get("choice") if f.get("choice") and not f.get("structure_review") else f.get("extracted_value")
        values = [excel(_norm(p.get("value"))) for p in f.get("parts") or []] or [excel(_norm(shown))]
        for value in filter(None, values):
            if not any(name in row or (f.get("parts") and value in row) for row in by_value.get(value, [])):
                missing.append((name, value))
        number = _norm((f.get("item") or {}).get("number"))
        if number and f.get("item_start") and not any(row and row[0] == number for row in rows):
            missing.append(("item #", number))
    for _, t in data["tables"]:
        missing += [("header", h) for h in _table_headers(t) if h and excel(h) not in by_value]
        missing += [("cell", _cell(c)) for r in t["rows"] for c in r["cells"] if _cell(c) and excel(_cell(c)) not in by_value]
    assert not missing, missing[:8]


_SOURCE_FIX = {"FAR52_html": 9}


@pytest.mark.parametrize("key", _per_doc(_SOURCE_FIX))
def test_source_references(key) -> None:
    """Every shown field points at its source: a page (and position) for a
    paged document, a DOM element for HTML. HTML never shows a page number."""

    data = built(key)
    for _, f in data["fields"]:
        if data["is_html"]:
            assert f.get("page") is None
            assert f.get("source_location") not in (None, "none"), f"no DOM reference for {f['label'][:40]!r}"
        else:
            assert f.get("page"), f"no page for {f['label'][:40]!r}"


@pytest.mark.parametrize("key", _per_doc({key: 9 for key in ALL}))
def test_completeness_outcome(key) -> None:
    """Processing finishing is not extraction completeness: every layout
    states one of three outcomes, and a document without a verified source
    inventory is never "verified complete"."""

    data = built(key)
    outcome = (data["layout"].get("completeness") or {}).get("status")
    assert outcome in {"verified_complete", "incomplete", "not_fully_verified"}
    if outcome == "verified_complete":
        assert data["layout"]["completeness"].get("inventory"), "complete without a source inventory"


# --- not yet regression-verified ----------------------------------------------


@pytest.mark.parametrize("form", sorted(REQUIRED_COVERAGE))
def test_form_without_real_sample(form) -> None:
    pytest.skip(f"{form}: not yet regression-verified — no real sample; required coverage: "
                + "; ".join(REQUIRED_COVERAGE[form]))
