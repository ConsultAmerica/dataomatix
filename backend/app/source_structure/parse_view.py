"""The Parse view: a document's complete content as typed, ordered,
source-located blocks, read from what is already stored.

    stored file text layer / persisted OCR word layer   (page_words)
      → reading-order blocks                            (reading_order.reconstruct_page)
      + accepted tables of the stored source structure  (load only, never rebuilt)
      + form boxes and tick boxes of that structure     (elements, linked to their block)
      + numbered sections and clauses of the page text  (clause_outline.build_outline)
      + additive labels: running header / footer, page reference, end-of-clause marginalia

Nothing here writes: no extraction, OCR or model call runs, the stored
structure is never rebuilt (an absent or out-of-date one is reported, not
replaced), and no coordinate is invented — a block without a source box
has `bbox: null` and says why. Every page in the requested window is
returned whole; the window is how a large document is paged.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.masking import redact_text
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.document_source_structure import DocumentSourceStructure
from app.source_structure.models import StructuredSourceDocument, TableCandidate
from app.source_structure.reading_order import reconstruct_page
from app.source_structure.service import (
    EXTRACTOR_VERSION,
    _open_source_pdf,
    _source_type,
    _text_only_blocks,
    page_words,
    stored_source_structure_is_current,
    table_accounts_for_its_words,
)

PARSE_VERSION = 1
DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 25

# A running header or footer sits in the top or bottom tenth of the page and
# repeats (digits aside) on at least this many pages, or this share of them.
_MARGIN = 0.1
_REPEAT_MIN_PAGES = 3
_REPEAT_MIN_SHARE = 0.3
_PAGE_REFERENCE = re.compile(r"^\s*(page\s+\d+(\s+of\s+\d+)?|\d+\s+of\s+\d+|-?\s*\d{1,4}\s*-?)\s*$", re.I)
# "Page 3 of 154" says what it is wherever it is printed; a bare "3" only in a margin.
_EXPLICIT_PAGE_REFERENCE = re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.I)
# "(End of clause)", "(End of Provision)", "(End of Section I)", "(End of Part 52)".
_END_MARKER = re.compile(r"^\s*\(\s*end of (clause|provision|section|part|subpart|attachment|exhibit)\b[^)]*\)\s*$", re.I)
_TOKEN = re.compile(r"\S+")
_MISSING_SHOWN = 20


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text.lower())).strip()


def _edge_lines(text: str, count: int) -> list[str]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[:count] + lines[-count:]


def running_lines(page_texts: list[str]) -> set[str]:
    """Lines (digits aside) that open or close many pages: running headers
    and footers. Read from the stored page text, so a window of pages is
    labelled the same way as the whole document."""

    counts: Counter[str] = Counter()
    for text in page_texts:
        counts.update({_normalized(line) for line in _edge_lines(text, 3)})
    needed = max(_REPEAT_MIN_PAGES, _REPEAT_MIN_SHARE * len(page_texts))
    return {line for line, seen in counts.items() if line and seen >= needed}


def _label(kind: str, text: str, bbox: list[float] | None, height: float | None, running: set[str]) -> str:
    """The block's type: its reading-order kind, or an additive label. A label
    never changes the text or where it sits — `source_kind` keeps the kind."""

    if kind == "table":
        return "table"
    if _END_MARKER.match(text):
        return "marginalia"
    if _EXPLICIT_PAGE_REFERENCE.match(text):
        return "page_reference"
    if bbox is None or not height:
        return kind
    top, bottom = bbox[1] / height, bbox[3] / height
    in_margin = bottom <= _MARGIN or top >= 1 - _MARGIN
    if in_margin and _PAGE_REFERENCE.match(text):
        return "page_reference"
    if in_margin and _normalized(text) in running:
        return "header" if bottom <= _MARGIN else "footer"
    return kind


def _structure(database: Session, document: Document) -> tuple[StructuredSourceDocument | None, dict]:
    """The stored source structure as it is — read, never rebuilt — and
    whether it matches the current extractor and inputs."""

    record = database.scalars(
        select(DocumentSourceStructure).where(DocumentSourceStructure.document_id == document.id)
    ).first()
    if record is None:
        return None, {"status": "missing", "extractor_version": None, "current_extractor_version": EXTRACTOR_VERSION}
    info = {"extractor_version": record.extractor_version, "current_extractor_version": EXTRACTOR_VERSION}
    try:
        structure = StructuredSourceDocument.model_validate(record.payload_json or {})
    except Exception:  # noqa: BLE001 - an unreadable stored structure is reported, not rebuilt
        return None, {**info, "status": "unreadable"}
    current = stored_source_structure_is_current(database, document)
    return structure, {**info, "status": "current" if current else "out_of_date"}


def _contains(box: list[float] | None, x: float, y: float) -> bool:
    return bool(box) and box[0] - 2 <= x <= box[2] + 2 and box[1] - 2 <= y <= box[3] + 2


def _element(field: dict, blocks: list[dict], mask: bool) -> dict:
    """A field of the Original File layout (the boxes and label/value pairs
    the app shows), linked to the block it is printed in. The printed value,
    what extraction read and the reviewed value stay separate."""

    anchor = field.get("value_bbox") or field.get("bbox")
    block_id = None
    if anchor:
        x, y = (anchor[0] + anchor[2]) / 2, (anchor[1] + anchor[3]) / 2
        block_id = next((b["id"] for b in blocks if _contains(b["bbox"], x, y)), None)
    item = field.get("item") or field.get("form_item") or {}
    shown = redact_text if mask else (lambda value: value)
    return {
        "id": field["id"],
        "type": "checkbox" if field.get("choice") else "form_field",
        "item_number": item.get("number") or None,
        "item_name": item.get("name") or None,
        "item_parent": item.get("parent") or None,
        "item_sub": item.get("sub") or field.get("sub_item") or None,
        "label": shown(field.get("label") or ""),
        "printed_value": shown(field.get("document_value") or ""),
        "extracted_value": shown(field.get("extracted_value") or ""),
        "reviewed_value": shown(field.get("effective_value") or ""),
        "blank": bool(field.get("blank")),
        "choice": field.get("choice"),
        "review_status": field.get("review_status"),
        "found_by": field.get("found_by"),
        "label_bbox": field.get("bbox"),
        "value_bbox": field.get("value_bbox"),
        "block_id": block_id,
    }


def _layout_fields(
    database: Session, document: Document, structure: StructuredSourceDocument | None, warnings: list
) -> list[dict] | None:
    """The Original File layout's fields, built over the loaded structure as
    original_layout_for builds them — without its rebuild step."""

    if structure is None:
        return None
    from app.models.document_metadata_field import DocumentMetadataField
    from app.models.structure_record_review import StructureRecordReview
    from app.source_structure.original_layout import _form_pages, build_original_layout

    try:
        metadata_rows = list(
            database.scalars(
                select(DocumentMetadataField)
                .where(DocumentMetadataField.document_id == document.id)
                .order_by(DocumentMetadataField.id)
            )
        )
        reviews = list(
            database.scalars(select(StructureRecordReview).where(StructureRecordReview.document_id == document.id))
        )
        box_pages = {c.page for c in structure.field_candidates if c.structural_relation == "ruled_form_box" and c.page}
        page_texts = {
            page.page_number: page.final_text or ""
            for page in database.scalars(
                select(DocumentPage).where(DocumentPage.document_id == document.id, DocumentPage.page_number.in_(box_pages))
            )
        } if box_pages else {}
        layout = build_original_layout(structure, metadata_rows, reviews, _form_pages(document, structure), page_texts)
    except Exception as exc:  # noqa: BLE001 - fields reported unavailable; the page text is still shown
        warnings.append(f"Form fields are unavailable for this document ({type(exc).__name__}).")
        return None
    return [
        item
        for section in layout.get("sections") or []
        for item in section.get("items") or []
        if item.get("kind") == "field" and not item.get("form_duplicate")
    ]


def _table_for(block: dict, tables: list[TableCandidate]) -> TableCandidate | None:
    if not block["bbox"]:
        return None
    x = (block["bbox"][0] + block["bbox"][2]) / 2
    y = (block["bbox"][1] + block["bbox"][3]) / 2
    return next((t for t in tables if _contains(list(t.bbox) if t.bbox else None, x, y)), None)


def _tokens(texts: list[str]) -> Counter:
    return Counter(token for text in texts for token in _TOKEN.findall(text))


def _chars(texts: list[str]) -> Counter:
    """Printed characters, spacing aside: "428 -" and "428-" hold the same."""
    return Counter(char for text in texts for char in text if not char.isspace())


def _words_inside(words: list, bbox) -> list:
    x0, y0, x1, y1 = bbox
    return [w for w in words if x0 - 2 <= (w.x0 + w.x1) / 2 <= x1 + 2 and y0 - 2 <= (w.y0 + w.y1) / 2 <= y1 + 2]


def _cell_texts(raw: dict) -> list[str]:
    return [cell for row in [raw["table"]["headers"], *raw["table"]["rows"]] for cell in row]


def _block_texts(raw: dict) -> list[str]:
    """What a block holds of the page: a table's cells plus, when the cells
    lost words, the table's own words (source_lines)."""
    if raw["kind"] == "table" and raw.get("table"):
        return _cell_texts(raw) + raw.get("source_lines", [])
    return [line.get("raw_text") or line["text"] for line in raw["lines"]]


def _with_raw_text(raw: dict) -> dict:
    """A line keeps its verbatim words when display cleanup (underline fill,
    "____ assigned") changed its text."""

    for line in raw["lines"]:
        words = line.get("words") or []
        verbatim = " ".join(word["text"] for word in words)
        if words and _chars([verbatim]) != _chars([line["text"]]):
            line["raw_text"] = verbatim
    return raw


def _split_end_markers(raw_blocks: list[dict]) -> list[dict]:
    """An "(End of clause)" line inside a paragraph stands as its own block
    (marginalia); the paragraph keeps every other line, in order."""

    out: list[dict] = []
    for raw in raw_blocks:
        lines = raw["lines"]
        if raw["kind"] == "table" or len(lines) < 2 or not any(_END_MARKER.match(line["text"]) for line in lines):
            out.append(raw)
            continue
        part: list[dict] = []
        for line in [*lines, None]:
            if line is not None and not _END_MARKER.match(line["text"]):
                part.append(line)
                continue
            for group in (part, [line] if line is not None else []):
                if not group:
                    continue
                boxes = [l["bbox"] for l in group if l.get("bbox")]
                bbox = (
                    [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
                    if boxes and raw.get("bbox") else None
                )
                out.append({"kind": raw["kind"], "text": "\n".join(l["text"] for l in group), "lines": group, "table": None, "bbox": bbox})
            part = []
    return out


def _page(
    page: DocumentPage,
    fitz_page,
    source_type: str,
    structure: StructuredSourceDocument | None,
    fields: list[dict] | None,
    running: set[str],
    mask: bool,
) -> dict:
    number = page.page_number
    height = page.page_height or (fitz_page.rect.height if fitz_page is not None else None)
    width = page.page_width or (fitz_page.rect.width if fitz_page is not None else None)
    tables: list[TableCandidate] = []
    if source_type == "html":
        text = page.final_text or ""
        raw_blocks = [
            {"kind": "paragraph", "text": p, "bbox": None, "lines": [{"text": line, "bbox": None} for line in p.splitlines()], "table": None}
            for p in (p.strip() for p in re.split(r"\n\s*\n", text)) if p
        ]
        positioning, method, source_texts = ("text_only" if text.strip() else "none"), "dom", [text]
        no_box = "HTML has no page coordinates; the block's place is its order in the source."
    else:
        words, method = page_words(page, fitz_page, get_settings().ocr_dpi)
        if words:
            if structure is not None:
                tables = [
                    t for t in structure.table_candidates
                    if t.page == number and table_accounts_for_its_words(t, words)
                ]
            raw_blocks = [block.as_dict() for block in reconstruct_page(words, tables)]
            positioning, source_texts = "spatial", [w.text for w in words]
            # A table's cells stand in for the words under it. Where the cells
            # dropped some (a merged header, stripped leaders or blanks, a
            # sentence split across cells), the table's own words are kept
            # beside them in reading order, and the shortfall is listed.
            for raw in raw_blocks:
                if raw["kind"] != "table" or not raw.get("bbox") or not raw.get("table"):
                    continue
                inside = _words_inside(words, raw["bbox"])
                lost = _chars([w.text for w in inside]) - _chars(_cell_texts(raw))
                if lost:
                    raw["source_lines"] = [line.text for b in reconstruct_page(inside) for line in b.lines]
                    raw["missing_in_cells"] = sorted(
                        (_tokens([w.text for w in inside]) - _tokens(_cell_texts(raw))).elements()
                    )[:_MISSING_SHOWN]
            no_box = None
        else:
            text = page.final_text or ""
            raw_blocks = _text_only_blocks(text)
            positioning = "text_only" if text.strip() else "none"
            method, source_texts = page.extraction_method or method, [text]
            no_box = "This page's stored text has no word positions; source highlighting is unavailable."

    raw_blocks = [_with_raw_text(raw) for raw in _split_end_markers(raw_blocks)]
    blocks: list[dict] = []
    for index, raw in enumerate(raw_blocks):
        text = raw["text"] if raw["kind"] != "table" else "\n".join(line["text"] for line in raw["lines"])
        block = {
            "id": f"p{number}.b{index}",
            "type": _label(raw["kind"], text, raw["bbox"], height, running),
            "source_kind": raw["kind"],
            "page": number,
            "index": index,
            "text": redact_text(text) if mask else text,
            "bbox": raw["bbox"],
            "lines": [
                {
                    "text": redact_text(line["text"]) if mask else line["text"],
                    "bbox": line.get("bbox"),
                    **({"raw_text": redact_text(line["raw_text"]) if mask else line["raw_text"]} if "raw_text" in line else {}),
                }
                for line in raw["lines"]
            ],
            "table": None,
            "locator": None if raw["bbox"] else (no_box or "No source box was recorded for this block."),
            "provenance": {"extraction_method": method, "positioning": positioning},
        }
        if raw["kind"] == "table" and raw.get("table"):
            candidate = _table_for(block, tables)
            cells = raw["table"]
            block["table"] = {
                "headers": [redact_text(c) for c in cells["headers"]] if mask else cells["headers"],
                "rows": [[redact_text(c) for c in row] for row in cells["rows"]] if mask else cells["rows"],
                "candidate_id": candidate.candidate_id if candidate else None,
                "continues_from": candidate.continuation.previous_candidate_id if candidate and candidate.continuation else None,
                "continues_to": candidate.continuation.next_candidate_id if candidate and candidate.continuation else None,
                # Present only when the cells did not hold every printed word.
                "source_lines": [redact_text(line) for line in raw["source_lines"]] if mask and "source_lines" in raw else raw.get("source_lines"),
                "missing_in_cells": raw.get("missing_in_cells", []) if not mask else [redact_text(token) for token in raw.get("missing_in_cells", [])],
            }
        blocks.append(block)

    # null: unavailable (no stored structure); []: none on this page.
    elements = None if fields is None else [_element(field, blocks, mask) for field in fields if field.get("page") == number]

    # Every printed character is somewhere in the blocks — or the shortfall is reported.
    held_texts = [text for raw in raw_blocks for text in _block_texts(raw)]
    held, source = _chars(held_texts), _chars(source_texts)
    missing = sum((source - held).values())
    lost_tokens = sorted((_tokens(source_texts) - _tokens(held_texts)).elements())
    return {
        "page_number": number,
        "width": width,
        "height": height,
        "positioning": positioning,
        "extraction_method": method,
        "blocks": blocks,
        "elements": elements,
        "completeness": {
            "source_characters": sum(source.values()),
            "block_characters": sum(held.values()),
            "missing_characters": missing,
            "missing_tokens": ([redact_text(t) for t in lost_tokens] if mask else lost_tokens)[:_MISSING_SHOWN] if missing else [],
            "tables_with_cell_gaps": sum(1 for raw in raw_blocks if raw.get("missing_in_cells")),
            "complete": missing == 0,
            # Text-only pages: a line with no letter or digit (a rule, an OCR speck) is not a block.
            "note": None if missing == 0 or positioning == "spatial" else "Lines without any letter or digit are left out of text-only pages.",
        },
    }


def _sections(page_texts: list[tuple[int, str]], first: int, last: int, mask: bool) -> dict:
    from app.services.clause_outline import build_outline

    outline = build_outline(page_texts)
    if outline["style"] == "none":
        return {"status": "none", "style": "none", "total": 0, "rows": []}
    keys = [column["key"] for column in outline["columns"]]
    heading_at = keys.index("heading") if "heading" in keys else None
    rows = [
        {
            "kind": record["kind"],
            "level": record["level"],
            "number": record["number"],
            "heading": (redact_text if mask else str)(record["cells"][heading_at]) if heading_at is not None else "",
            "page_start": record["page_start"],
        }
        for record in outline["records"]
        if record["kind"] in {"section", "clause", "paragraph"}
    ]
    return {
        "status": "available",
        "style": outline["style"],
        "total": len(rows),
        "rows": [row for row in rows if first <= row["page_start"] <= last],
    }


def parse_document(
    database: Session,
    document: Document,
    *,
    start_page: int = 1,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    mask: bool = False,
) -> dict[str, Any]:
    page_limit = max(1, min(page_limit, MAX_PAGE_LIMIT))
    pages = list(
        database.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id).order_by(DocumentPage.page_number)
        )
    )
    numbers = [page.page_number for page in pages]
    window = [page for page in pages if page.page_number >= start_page][:page_limit]
    source_type = _source_type(document)
    structure, structure_info = _structure(database, document)
    warnings: list[str] = []
    if structure_info["status"] != "current":
        warnings.append(
            {
                "missing": "No source structure is stored for this document: tables and form boxes are unavailable here, and page text is shown without them.",
                "unreadable": "The stored source structure could not be read: tables and form boxes are unavailable here.",
                "out_of_date": "The stored source structure is from an earlier extraction; it is shown as stored, not rebuilt.",
            }[structure_info["status"]]
        )
    page_texts = [(page.page_number, page.final_text or "") for page in pages]
    running = running_lines([text for _, text in page_texts])

    fields = _layout_fields(database, document, structure, warnings) if window else None
    fitz_doc = _open_source_pdf(document, source_type, warnings) if source_type != "html" and window else None
    try:
        out_pages = []
        for page in window:
            fitz_page = (
                fitz_doc[page.page_number - 1]
                if fitz_doc is not None and 0 <= page.page_number - 1 < fitz_doc.page_count
                else None
            )
            out_pages.append(_page(page, fitz_page, source_type, structure, fields, running, mask))
    finally:
        if fitz_doc is not None:
            fitz_doc.close()

    last = window[-1].page_number if window else start_page - 1
    later = [n for n in numbers if n > last]
    return {
        "parse_version": PARSE_VERSION,
        "document": {
            "id": document.id,
            "filename": document.original_filename,
            "content_type": document.content_type,
            "source_type": source_type,
            "checksum_sha256": document.checksum_sha256,
            "page_count": len(pages),
            "processing_status": document.processing_status,
        },
        # The processing run these blocks come from: the stored file (checksum)
        # and the stored structure's extractor version.
        "run": {"checksum_sha256": document.checksum_sha256, "structure": structure_info},
        "window": {
            "start_page": window[0].page_number if window else None,
            "end_page": last if window else None,
            "page_limit": page_limit,
            "next_start_page": later[0] if later else None,
            "total_pages": len(pages),
        },
        "pages": out_pages,
        "sections": _sections(page_texts, window[0].page_number, last, mask) if window else {"status": "none", "style": "none", "total": 0, "rows": []},
        "masking": {
            "applied": mask,
            "rule": "Identifier shapes (SSN, long digit runs, IBAN, MRZ) are masked for callers who cannot export." if mask else None,
        },
        "warnings": warnings,
    }
