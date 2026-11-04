"""The Parse view as a file, laid out as the original reads: every page in
order, each printed line on its own row and each table in real cells. Built
only from parse_document, so a download holds what the Parse page shows and,
like it, never extracts, OCRs or rebuilds anything.

Rows carry their page, block number and block type, so a value in the file
can be traced back to its place in the document.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Iterator
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.document import Document
from app.source_structure.parse_view import MAX_PAGE_LIMIT, parse_document
from app.staging.export import _xlsx_value

_TYPE_LABELS = {
    "heading": "Heading",
    "paragraph": "Text",
    "table": "Table",
    "header": "Header",
    "footer": "Footer",
    "page_reference": "Page number",
    "marginalia": "Marginalia",
}
LEADING_COLUMNS = ["Page", "Block", "Type"]
# Content columns a long line wraps across, and roughly what fits in them.
_MIN_CONTENT_COLUMNS = 4
_CONTENT_WIDTH = 28
_WRAP_AT = 110
_LINE_HEIGHT = 15
_MAX_ROW_HEIGHT = 409
# "-5.00" stays a number; "- Logistics" is text Excel would read as a formula.
_SIGNED_NUMBER = re.compile(r"^-\s*[\d.,]+%?$")


@dataclass
class Row:
    page: int | None
    block: int | None
    type: str
    cells: list[str]
    role: str = "text"  # text | heading | table_header | table_cell | note
    first_of_page: bool = False


def _all_pages(database: Session, document: Document) -> tuple[list[dict], list[str]]:
    pages: list[dict] = []
    warnings: list[str] = []
    start: int | None = 1
    while start is not None:
        body = parse_document(database, document, start_page=start, page_limit=MAX_PAGE_LIMIT, mask=False)
        pages.extend(body["pages"])
        warnings.extend(warning for warning in body["warnings"] if warning not in warnings)
        start = body["window"]["next_start_page"]
    return pages, warnings


def _block_rows(block: dict, number: int) -> Iterator[Row]:
    page, label = block["page"], _TYPE_LABELS.get(block["type"], block["type"])
    table = block.get("table")
    if block["type"] == "table" and table:
        if table["headers"]:
            yield Row(page, number, label, list(table["headers"]), "table_header")
        for cells in table["rows"]:
            yield Row(page, number, label, list(cells), "table_cell")
        # Printed words the cells did not hold are kept, never dropped.
        for line in table.get("source_lines") or []:
            yield Row(page, number, "Table text", [line], "note")
        return
    lines = [line.get("raw_text") or line["text"] for line in block.get("lines") or []] or block["text"].splitlines()
    for line in lines:
        yield Row(page, number, label, [line], "heading" if block["type"] == "heading" else "text")


def build_rows(database: Session, document: Document) -> list[Row]:
    """Warnings first, then every page's blocks. Blocks are numbered through
    the whole document, as a reader counts them."""

    pages, warnings = _all_pages(database, document)
    rows = [Row(None, None, "Note", [warning], "note") for warning in warnings]
    number = 0
    for page in pages:
        first = True
        for block in page["blocks"]:
            number += 1
            for row in _block_rows(block, number):
                row.first_of_page = first
                first = False
                rows.append(row)
        completeness = page["completeness"]
        if not completeness["complete"] and completeness["missing_tokens"]:
            words = " ".join(completeness["missing_tokens"])
            rows.append(Row(page["page_number"], None, "Note",
                            [f"{completeness['missing_characters']} printed characters are not in any block: {words}"], "note"))
    return rows


def _csv_safe(value: str) -> str:
    """Spreadsheet-safe: text starting like a formula is never executed."""

    if value[:1] in ("=", "+", "@") or (value[:1] == "-" and not _SIGNED_NUMBER.match(value)):
        return "'" + value
    return value


def build_parse_csv(rows: list[Row]) -> str:
    width = max((len(row.cells) for row in rows), default=1)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([*LEADING_COLUMNS, *(f"Content {index}" for index in range(1, width + 1))])
    for row in rows:
        writer.writerow(["" if row.page is None else row.page, "" if row.block is None else row.block, row.type,
                         *(_csv_safe(cell) for cell in row.cells)])
    return buffer.getvalue()


def _lines_needed(text: str, fits: int) -> int:
    return sum(max(1, math.ceil(len(part) / fits)) for part in text.split("\n")) if text else 1


def build_parse_xlsx(rows: list[Row], title: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    book = Workbook()
    sheet = book.active
    sheet.title = "Parsed document"
    lead = len(LEADING_COLUMNS)
    content = max([_MIN_CONTENT_COLUMNS, *(len(row.cells) for row in rows if row.role.startswith("table"))])
    last = lead + content

    muted = Font(color="64748B", size=9)
    band = PatternFill("solid", fgColor="E8F1FE")
    header_fill = PatternFill("solid", fgColor="EEF2F6")
    side = Side(style="thin", color="CBD5E1")
    box = Border(left=side, right=side, top=side, bottom=side)
    top = Alignment(vertical="top")
    wrap = Alignment(vertical="top", wrap_text=True)

    for index, name in enumerate(LEADING_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=index, value=name)
        cell.font = Font(bold=True)
        cell.fill = header_fill
    sheet.cell(row=1, column=lead + 1, value=title).font = Font(bold=True)
    for index in range(lead + 1, last + 1):
        sheet.cell(row=1, column=index).fill = header_fill
    sheet.freeze_panes = sheet.cell(row=2, column=lead + 1)
    for index, width in enumerate((6, 6, 12), start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for index in range(lead + 1, last + 1):
        sheet.column_dimensions[get_column_letter(index)].width = _CONTENT_WIDTH

    at = 2
    for row in rows:
        if row.first_of_page:
            cell = sheet.cell(row=at, column=1, value=f"Page {row.page}")
            cell.font = Font(bold=True, color="0D47A8")
            for index in range(1, last + 1):
                sheet.cell(row=at, column=index).fill = band
            at += 1
        for index, value in enumerate((row.page, row.block, row.type), start=1):
            cell = sheet.cell(row=at, column=index, value=value)
            cell.font = muted
            cell.alignment = top
        is_table = row.role in {"table_header", "table_cell"}
        for offset, text in enumerate(row.cells):
            cell = sheet.cell(row=at, column=lead + 1 + offset)
            cell.value = _xlsx_value(text)
            # Stored as text as printed: a line starting "=" is not a formula.
            cell.data_type = "s"
            cell.alignment = wrap if is_table else top
            if is_table:
                cell.border = box
            if row.role == "table_header":
                cell.font = Font(bold=True)
                cell.fill = header_fill
            elif row.role == "heading":
                cell.font = Font(bold=True)
            elif row.role == "note":
                cell.font = Font(italic=True, color="7A4A08")
        if is_table:
            needed = max((_lines_needed(text, _CONTENT_WIDTH - 2) for text in row.cells), default=1)
            sheet.row_dimensions[at].height = min(_MAX_ROW_HEIGHT, needed * _LINE_HEIGHT)
        elif row.cells and len(row.cells[0]) > _WRAP_AT:
            # A line wider than the page (HTML paragraphs): wrapped across the columns.
            sheet.merge_cells(start_row=at, start_column=lead + 1, end_row=at, end_column=last)
            sheet.cell(row=at, column=lead + 1).alignment = wrap
            fits = max(_WRAP_AT, content * (_CONTENT_WIDTH - 1))
            sheet.row_dimensions[at].height = min(_MAX_ROW_HEIGHT, _lines_needed(row.cells[0], fits) * _LINE_HEIGHT)
        at += 1

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
