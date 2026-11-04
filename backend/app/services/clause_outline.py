"""A document's sections and clauses as rows: section, clause or paragraph
number, parent, heading and the original text under it.

Read from the stored page text — the same text the Full Text view shows —
so it adds no extraction of its own. Table-of-contents pages are left out
(their entries are only used to check that every listed section was found
in the body). A clause's text runs on across page breaks until the next
heading; running page footers are skipped. Words are never rewritten,
summarised or cut: a row holds the text exactly as stored, with only the
lines a page break split joined back.

Two numbering styles:
- FAR Parts ("7.000 Scope of part.", "Subpart 7.1 - …"): the headings the
  FAR text parser finds (app/far/text.py), with each lettered paragraph
  "(a)", "(b)" … as its own row under the section.
- Solicitations and contracts ("Section B …", "B.1 Background",
  "C.5.1.1 HVAC Maintenance"): every numbered heading, its parent being
  the number one level up.

Checks, never corrections: contents entries not found in the body, gaps in
a clause or paragraph sequence (B.3.2 then B.3.4), and headings with no
text are reported for a person to look at.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from app.far import text as far_text
from app.services.section_text import _CONTENTS_LINE, _LEADERS, _RUNNING_HEAD, _is_contents_page

# "B.1 Background", "C.5.1.1 HVAC Maintenance (Required Service)", "AA.2 …".
# "M.6.2- Pricing Evaluation" too.
_NUMBERED = re.compile(r"^\s*(?P<number>[A-Z]{1,2}\.\d+(?:\.\d+)*)\.?(?:\s*[-–—])?\s+(?P<title>[A-Z(\"“'‘].*?)\s*$")
# "Section B Services, Ordering and Prices", "Section C – Description/…".
_SECTION = re.compile(r"^\s*Section\s+(?P<letter>[A-M])(?![.\w])\s*[-–—:]?\s*(?P<title>\S.*?)?\s*$")
# A paragraph of a FAR section: "(a) Developing acquisition plans;".
_LETTERED = re.compile(r"^\((?P<letter>[a-z]{1,2})\)\s*")
_MAX_HEADING = 160
_WORD = re.compile(r"[^\W_]+")
# A page's running header: a "Section X" this close to the top starts it.
_PAGE_HEAD_LINES = 6
# Column gaps: a line laid out as a table row, not a heading.
_COLUMNS = re.compile(r"\S\s{3,}\S")
# A paragraph that runs on to the next page: no closing punctuation, and
# the next page carries on in lower case.
_ENDS_SENTENCE = re.compile(r"[.;:!?)\]\"”’—–-]\s*$")


@dataclass
class OutlineRow:
    section: str  # the top clause: "B.1", "C.5", "7.000", "Section B", "Subpart 7.1"
    number: str  # this row's own number: "B.1.1", "(a)"; the section's number for the section row
    parent: str | None
    level: int
    kind: str  # "section" | "clause" | "paragraph"
    heading: str
    content: str
    page_start: int
    page_end: int
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "section": self.section,
            "number": self.number,
            "parent": self.parent,
            "level": self.level,
            "kind": self.kind,
            "heading": self.heading,
            "content": self.content,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "characters": len(self.content),
            "issues": self.issues,
        }


def _words(text: str) -> Counter:
    return Counter(_WORD.findall(text))


def _coverage(body: Counter, held: Counter) -> dict:
    """Every word of the body (contents pages, running footers and the FAR
    "Parent topic" line aside) is in some cell of the dataset: the words of
    the body it doesn't hold are counted, never dropped quietly."""

    missing = body - held
    return {"body_words": sum(body.values()), "missing_words": sum(missing.values()),
            "missing_examples": [word for word, _ in missing.most_common(10)]}


def _letter_index(letters: str) -> int:
    """a=1 … z=26, aa=27 (FAR doubles letters after z)."""

    return (ord(letters[0]) - 96) + (26 if len(letters) == 2 else 0)


def _letter(index: int) -> str:
    return chr(96 + index) if index <= 26 else chr(96 + index - 26) * 2


def _join_across_pages(paras: list[far_text.Paragraph]) -> list[far_text.Paragraph]:
    """A paragraph the page break split, joined back: it doesn't end a
    sentence and the next page starts in lower case."""

    out: list[far_text.Paragraph] = []
    for para in paras:
        last = out[-1] if out else None
        if (last and para.page > last.page and para.text[:1].islower() and not _ENDS_SENTENCE.search(last.text)):
            out[-1] = far_text.Paragraph(last.page, f"{last.text} {para.text}")
            continue
        out.append(para)
    return out


def _far_outline(pages: list[tuple[int, str]]) -> dict | None:
    paras = [p for p in far_text.paragraphs(pages) if not _RUNNING_HEAD.match(p.text)]
    part, _part_heading = far_text._part_of(paras)
    if part is None:
        return None
    headings, body_start = far_text._find_headings(paras, part)
    if not headings:
        return None
    contents, _ = far_text._toc(paras, part)
    rows: list[OutlineRow] = []
    checks: list[dict] = []
    subpart: str | None = None
    for position, heading in enumerate(headings):
        stop = headings[position + 1].index if position + 1 < len(headings) else len(paras)
        body = _join_across_pages([p for p in paras[heading.end:stop] if not far_text._PARENT_TOPIC.match(p.text)])
        last_page = body[-1].page if body else heading.page
        title = far_text._strip_title(heading.title)
        if heading.number.startswith("Subpart"):
            subpart = heading.number
            rows.append(OutlineRow(heading.number, heading.number, None, 0, "section", title,
                                   "\n\n".join(p.text for p in body), heading.page, last_page))
            continue
        intro: list[far_text.Paragraph] = []
        lettered: list[tuple[str, list[far_text.Paragraph]]] = []
        expected = 1
        for para in body:
            match = _LETTERED.match(para.text)
            # A new lettered paragraph is the next letter (or one after it,
            # a skipped letter); "(i)" after "(h)" is a letter, otherwise a
            # roman sub-item of the paragraph it is in.
            if match and _letter_index(match.group("letter")) in (expected, expected + 1):
                index = _letter_index(match.group("letter"))
                if index == expected + 1:
                    checks.append({"code": "sequence_gap", "number": f"{heading.number}({_letter(expected)})",
                                   "message": f"{heading.number}: paragraph ({_letter(expected)}) isn't in the text — "
                                              f"({_letter(expected - 1) if expected > 1 else ''}) is followed by ({match.group('letter')})."})
                expected = index + 1
                lettered.append((f"({match.group('letter')})", [far_text.Paragraph(para.page, para.text[match.end():])]))
            elif lettered:
                lettered[-1][1].append(para)
            else:
                intro.append(para)
        row = OutlineRow(heading.number, heading.number, subpart, 1, "clause", title,
                         "\n\n".join(p.text for p in intro), heading.page, (intro[-1].page if intro else heading.page))
        if not intro and not lettered:
            row.issues.append("This heading has no text of its own.")
        rows.append(row)
        for number, paragraphs in lettered:
            rows.append(OutlineRow(heading.number, number, heading.number, 2, "paragraph", "",
                                   "\n\n".join(p.text for p in paragraphs), paragraphs[0].page, paragraphs[-1].page))
    found = {heading.number for heading in headings}
    for number, title in contents:
        if number not in found:
            checks.append({"code": "not_in_body", "number": number,
                           "message": f"{number} {title} is in the table of contents but wasn't found in the text."})
    contents_pages = sorted({p.page for p in paras[:body_start]}) if body_start else []
    body_words = Counter()
    for para in paras[body_start:]:
        if not far_text._PARENT_TOPIC.match(para.text):
            body_words += _words(para.text)
    return {"style": "far", "rows": rows, "checks": checks, "contents_pages": contents_pages, "body_words": body_words}


def _parent_of(number: str) -> str | None:
    """"B.1.2" → "B.1"; "B.1" → "Section B"."""

    parts = number.split(".")
    return ".".join(parts[:-1]) if len(parts) > 2 else f"Section {parts[0]}"


def _contents_entries(pages: list[tuple[int, str]]) -> list[tuple[str, str]]:
    entries = []
    for _number, text in pages:
        for line in text.splitlines():
            if not _CONTENTS_LINE.search(line):
                continue
            title = _LEADERS.sub(" ", re.sub(r"\d{1,4}\s*$", "", line)).strip()
            match = _NUMBERED.match(title)
            if match:
                entries.append((match.group("number"), match.group("title").rstrip(" :")))
    return entries


def _numbered_outline(pages: list[tuple[int, str]]) -> dict | None:
    contents_pages = [number for number, text in pages if _is_contents_page(text)]
    contents = _contents_entries([(n, t) for n, t in pages if n in contents_pages])
    rows: list[OutlineRow] = []
    lines: list[str] = []
    current: OutlineRow | None = None

    def close() -> None:
        if current is not None:
            current.content = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
            if not current.content and current.kind != "section":
                current.issues.append("This heading has no text of its own.")
            rows.append(current)

    section_letter: str | None = None
    body_words: Counter = Counter()
    used: set[str] = set()
    explicit_sections = sum(1 for number, text in pages if number not in contents_pages
                            for line in text.splitlines() if _SECTION.match(line.strip())) >= 2
    for page_number, text in pages:
        if page_number in contents_pages:
            continue
        seen_on_page = 0
        for line in text.splitlines():
            if _RUNNING_HEAD.match(line) or _CONTENTS_LINE.search(line):
                continue
            body_words.update(_WORD.findall(line))
            stripped = line.strip()
            top_of_page = seen_on_page < _PAGE_HEAD_LINES
            section = _SECTION.match(stripped) if len(stripped) <= _MAX_HEADING else None
            if section and section_letter and section.group("letter") <= section_letter and not top_of_page:
                # "Section J and Price Template …" wrapped inside Section L: sections
                # only go forward, unless a page starts with one (an attached part).
                section = None
            if stripped:
                seen_on_page += 1
            numbered = _NUMBERED.match(stripped) if len(stripped) <= _MAX_HEADING and not section else None
            if numbered and _COLUMNS.search(numbered.group("title")):
                # "G.3.8     Mergers, …     If applicable, SF30 …": a table row.
                numbered = None
            if numbered and section_letter and not numbered.group("number").startswith(section_letter + "."):
                # "M.4.1 …" printed inside Section L isn't a heading of it. With
                # "Section X" headings, a clause belongs to the section it is in;
                # without them, the next letter starts the next section.
                if explicit_sections or numbered.group("number")[0] != chr(ord(section_letter) + 1):
                    numbered = None
            if numbered and numbered.group("number") in used:
                # "M.4.3 Section 3 …" again in a scoring table: a row of that table.
                numbered = None
            if section:
                close()
                lines = []
                if section_letter and section.group("letter") <= section_letter:
                    used = set()  # an attached part numbers its clauses again
                section_letter = section.group("letter")
                current = OutlineRow(f"Section {section_letter}", f"Section {section_letter}", None, 0, "section",
                                     (section.group("title") or "").strip(), "", page_number, page_number)
                continue
            if numbered:
                number = numbered.group("number")
                used.add(number)
                section_letter = number.split(".")[0]
                close()
                lines = []
                parts = number.split(".")
                top = ".".join(parts[:2])
                current = OutlineRow(top, number, _parent_of(number), len(parts) - 1, "clause",
                                     numbered.group("title").rstrip(" :"), "", page_number, page_number)
                continue
            if current is None:
                # The cover and anything else before the first heading.
                current = OutlineRow("", "", None, 0, "front", "Before the first section", "", page_number, page_number)
            lines.append(line.rstrip())
            if stripped:
                current.page_end = page_number
    close()
    rows = [row for row in rows if row.kind != "front" or row.content]
    if sum(1 for row in rows if row.kind == "clause") < 3:
        return None
    checks: list[dict] = []
    found = {row.number for row in rows}
    for number, title in contents:
        if number not in found:
            checks.append({"code": "not_in_body", "number": number,
                           "message": f"{number} {title} is in the table of contents but wasn't found in the text."})
    # Siblings numbered in order: a skipped number is reported, not filled in.
    last_child: dict[str, int] = {}
    for row in rows:
        if row.kind != "clause":
            continue
        parent, last = row.number.rsplit(".", 1)
        if not last.isdigit():
            continue
        previous = last_child.get(parent)
        if previous is not None and int(last) > previous + 1:
            missing = ", ".join(f"{parent}.{n}" for n in range(previous + 1, int(last)))
            checks.append({"code": "sequence_gap", "number": f"{parent}.{previous + 1}",
                           "message": f"{missing} isn't in the document — {parent}.{previous} is followed by {row.number}."})
        last_child[parent] = max(previous or 0, int(last))
    return {"style": "numbered", "rows": rows, "checks": checks, "contents_pages": contents_pages, "body_words": body_words}


def build_outline(pages: Iterable[tuple[int, str]], tables: Iterable[dict] = ()) -> dict:
    """The outline of a document's stored page text, or style "none" when
    it has no numbered sections to show. `tables` are the tables the
    document's structure already holds (original_layout); each is placed
    under the clause it is printed in. `columns` and `records` are what the
    Extracted Data view and the Excel export both show."""

    ordered = sorted(((number, text or "") for number, text in pages), key=lambda page: page[0])
    outline = _far_outline(ordered) or _numbered_outline(ordered)
    if outline is None:
        return {"style": "none", "columns": [], "records": [], "checks": [], "contents_pages": [], "coverage": None}
    rows = outline["rows"]
    for position, row in enumerate(rows):
        # "[Reserved]", or a heading whose text is all in its subsections
        # ("7.107" over "7.107-1", "C.5" over "C.5.1"): nothing is missing.
        following = rows[position + 1] if position + 1 < len(rows) else None
        if "reserved" in row.heading.lower() or (following and following.number.startswith((row.number + ".", row.number + "-"))):
            row.issues = [issue for issue in row.issues if "no text" not in issue]
        for issue in row.issues:
            outline["checks"].append({"code": "no_text", "number": row.number, "message": f"{row.number} {row.heading}: {issue}"})
    placed = _place_tables(rows, list(tables))
    columns, records = _records(outline["style"], rows, placed)
    held: Counter = Counter()
    for record in records:
        for value in record["cells"]:
            if isinstance(value, str):
                held.update(_WORD.findall(value))
    return {
        "style": outline["style"],
        "columns": columns,
        "records": records,
        "checks": outline["checks"],
        "contents_pages": outline["contents_pages"],
        "coverage": _coverage(outline["body_words"], held),
    }


# --- tables -----------------------------------------------------------------------------------


def _cell_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _table_rows(table: dict) -> list[tuple[int, list[str]]]:
    first_page = (table.get("pages") or [0])[0]
    return [(row.get("page") or first_page, [_cell_text(cell) for cell in row.get("cells") or []]) for row in table.get("rows") or []]


def _place_tables(rows: list[OutlineRow], tables: list[dict]) -> dict[int, list[dict]]:
    """Each table under the clause it is printed in: on its page, with its
    cells in the clause's text."""

    placed: dict[int, list[dict]] = {}
    number = 0
    for table in sorted(tables, key=lambda item: ((item.get("pages") or [0])[0], item.get("id") or "")):
        body = _table_rows(table)
        headers = [_cell_text(header) for header in table.get("headers") or []]
        if not body and not headers:
            continue
        page = (table.get("pages") or [body[0][0] if body else 0])[0]
        sample = [cell for _, cells in body[:3] for cell in cells if len(cell) >= 3][:6]
        candidates = [index for index, row in enumerate(rows) if row.page_start <= page <= row.page_end and row.kind != "front"]
        if not candidates:
            before = [index for index, row in enumerate(rows) if row.page_start <= page]
            if not before:
                continue
            candidates = before[-1:]
        flat = {index: re.sub(r"\s+", " ", rows[index].content) for index in candidates}
        best = max(candidates, key=lambda index: (sum(cell in flat[index] for cell in sample), index))
        number += 1
        rows[best].content = _take_out_table(rows[best].content, headers, body, number)
        placed.setdefault(best, []).append({"number": number, "title": _cell_text(table.get("title")), "headers": headers,
                                            "rows": body, "page": page, "record_key": table.get("record_key")})
    return placed


def _take_out_table(content: str, headers: list[str], body: list[tuple[int, list[str]]], number: int) -> str:
    """The table's lines out of the clause text, so it isn't shown twice —
    only when the table's cells hold every word of those lines (most of
    the table's words, nothing else), so nothing is lost."""

    budget = _words(" ".join(headers + [cell for _, cells in body for cell in cells]))
    total = sum(budget.values())
    if not total:
        return content
    lines = content.split("\n")
    best: tuple[int, int, int] | None = None  # (words taken, first line, line after)
    for start in range(len(lines)):
        if not _WORD.search(lines[start]):
            continue
        remaining, taken, end = budget.copy(), 0, start
        for index in range(start, len(lines)):
            words = _words(lines[index])
            if words - remaining:
                break
            remaining -= words
            taken += sum(words.values())
            end = index + 1
        if end - start >= 2 and (best is None or taken > best[0]):
            best = (taken, start, end)
    if best is None or best[0] < 0.9 * total:
        return content
    _, start, end = best
    return "\n".join([*lines[:start], f"[Table {number} — in the rows below]", *lines[end:]]).strip("\n")


# --- the dataset the Extracted Data view and the Excel export both show -----------------------

_BASE = [("section", "Section Number"), ("number", "Paragraph Number"), ("heading", "Heading"), ("content", "Full Content"), ("page", "PDF Page")]


# A table "title" that is really the line above the table: a section's
# closing line, or a clause heading.
_NOT_A_TITLE = re.compile(r"^\s*(?:\(End of\b|Section\s+[A-M]\b|[A-Z]{1,2}\.\s?\d+(?:\.\d+)*\b)", re.I)
# A line that starts an item of its own: "(a)", "(1)", "1.", "a.", a bullet, a table marker.
_ITEM = re.compile(r"^\s*(?:\(\w{1,4}\)|\d{1,3}[.)]\s|[a-z][.)]\s|[●•▪◦·]|\[Table\b)")


def _joined(text: str) -> str:
    """The lines a PDF wrapped joined back into their paragraph; a block laid
    out in columns or as a bulleted list stays as stored. Only line breaks
    change — every word stays, in order."""

    blocks = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if any(_COLUMNS.search(line.strip()) for line in lines) or any(re.match(r"^\s*[●•▪◦]", line) for line in lines):
            blocks.append("\n".join(lines))
            continue
        out: list[str] = []
        for line in (line.strip() for line in lines):
            if out and not _ITEM.match(line):
                out[-1] = f"{out[-1]}{line}" if re.search(r"[A-Za-z]-$", out[-1]) and line[:1].isalpha() else f"{out[-1]} {line}"
            else:
                out.append(line)
        blocks.append("\n".join(out))
    return "\n\n".join(blocks)


def _page_text(start: int, end: int) -> str:
    return f"{start}" if start == end else f"{start}–{end}"


def _records(style: str, rows: list[OutlineRow], placed: dict[int, list[dict]]) -> tuple[list[dict], list[dict]]:
    """Columns 1–5 always; 6 and on only when the document has them: the
    parent clause of nested numbering, the FAR subpart, and one column per
    table column. A section's own row leaves Paragraph Number empty
    ("B.1 | | Background")."""

    extra: list[tuple[str, str]] = []
    if style == "numbered" and any(row.level > 1 for row in rows):
        extra.append(("parent", "Parent Clause"))
    if style == "far":
        extra.append(("subpart", "Subpart"))
    width = max((max([len(table["headers"]), *(len(cells) for _, cells in table["rows"])])
                 for tables in placed.values() for table in tables), default=0)
    columns = [{"key": key, "label": label} for key, label in [*_BASE, *extra]]
    columns += [{"key": f"t{index + 1}", "label": f"Table Column {index + 1}"} for index in range(width)]
    keys = [column["key"] for column in columns]
    subparts = {row.number: f"{row.number} - {row.heading}" for row in rows if row.number.startswith("Subpart")}
    section_subpart = {row.number: subparts.get(row.parent or "", "") for row in rows if row.kind == "clause"}

    def record(kind: str, values: dict, row: OutlineRow, level: int, page: int, key: str | None = None) -> dict:
        return {"kind": kind, "level": level, "number": row.number, "page_start": page, "record_key": key,
                "cells": [values.get(k, "") for k in keys]}

    records: list[dict] = []
    for index, row in enumerate(rows):
        if row.number.startswith("Subpart") and not row.content and index not in placed:
            continue  # its title is in the Subpart column of each row under it
        subpart = subparts.get(row.number, "") if row.number.startswith("Subpart") else section_subpart.get(row.section, "")
        values = {"section": row.section, "number": row.number if row.number != row.section else "", "heading": row.heading,
                  "content": _joined(row.content), "page": _page_text(row.page_start, row.page_end), "parent": row.parent or "", "subpart": subpart}
        records.append(record(row.kind, values, row, row.level, row.page_start))
        for table in placed.get(index, []):
            base = {"section": row.section, "number": values["number"], "parent": values["parent"], "subpart": subpart}
            title = "" if _NOT_A_TITLE.match(table["title"]) else table["title"]
            records.append(record("table_header", {**base, "heading": f"Table {table['number']}", "content": title, "page": str(table["page"]),
                                                   **{f"t{i + 1}": header for i, header in enumerate(table["headers"])}},
                                  row, row.level + 1, table["page"], table["record_key"]))
            for page, cells in table["rows"]:
                records.append(record("table_row", {**base, "page": str(page), **{f"t{i + 1}": cell for i, cell in enumerate(cells)}},
                                      row, row.level + 1, page, table["record_key"]))
    return columns, records


# --- Excel ------------------------------------------------------------------------------------

_CELL = 32_000  # under Excel's 32,767-character cell limit
_INVALID_SHEET = re.compile(r"[\[\]:*?/\\]")


def _write_sheet(wb, outline: dict, filename: str, title: str) -> None:
    """One document's dataset: the same columns, column names, row order and
    values as its Extracted Data view. Text longer than an Excel cell
    carries on in the row under it ("continued 2 of 3") — nothing is cut."""

    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from app.staging.export import _XLSX_ILLEGAL

    ws = wb.create_sheet(title)
    keys = [column["key"] for column in outline["columns"]]
    excluded = outline["contents_pages"]
    ws.append([f"Extracted Data — {filename}"])
    ws.append([(f"Table of contents (page{'s' if len(excluded) != 1 else ''} {', '.join(map(str, excluded))}) left out. " if excluded else "")
               + "Text as stored in the document, not rewritten."])
    ws.append([])
    ws.append([column["label"] for column in outline["columns"]])
    header_row = ws.max_row
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"].font = Font(italic=True, size=9, color="44546A")
    for cell in ws[header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3864")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    soft = PatternFill("solid", fgColor="EEF2F8")
    content_at, heading_at = keys.index("content"), keys.index("heading")
    for record in outline["records"]:
        cells = [_XLSX_ILLEGAL.sub(" ", value) if isinstance(value, str) else value for value in record["cells"]]
        content = cells[content_at] or ""
        parts = [content[start:start + _CELL] for start in range(0, len(content), _CELL)] or [""]
        for part_index, part in enumerate(parts):
            line = list(cells) if part_index == 0 else ["" for _ in cells]
            if part_index:
                line[0], line[1] = cells[0], cells[1]
                line[heading_at] = f"{cells[heading_at]} (continued {part_index + 1} of {len(parts)})"
            line[content_at] = part
            ws.append(line)
            for cell in ws[ws.max_row]:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if record["kind"] in ("section", "table_header"):
                    cell.font = Font(bold=True)
                    cell.fill = soft
    widths = {"section": 14, "number": 14, "heading": 34, "content": 90, "page": 10, "parent": 14, "subpart": 36}
    for index, key in enumerate(keys, start=1):
        ws.column_dimensions[get_column_letter(index)].width = widths.get(key, 24)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(keys))}{ws.max_row}"


def build_outline_xlsx(outlines: list[tuple[str, dict]]) -> bytes:
    """One sheet per document, as its Extracted Data view shows it, and a
    Checks sheet with what each one flags for review."""

    import io

    from openpyxl import Workbook

    from app.staging.xlsx_style import write_table_sheet

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    without = [name for name, outline in outlines if outline["style"] == "none"]
    outlines = [(name, outline) for name, outline in outlines if outline["style"] != "none"]
    for name, outline in outlines:
        title = "Extracted Data"
        if len(outlines) > 1:
            base = _INVALID_SHEET.sub(" ", re.sub(r"\.[A-Za-z0-9]{2,5}$", "", name)).strip()[:28] or "Document"
            title, suffix = base, 2
            while title.lower() in used:
                title, suffix = f"{base[:24]} ({suffix})", suffix + 1
            used.add(title.lower())
        _write_sheet(wb, outline, name, title)
    checks = [[name, check["number"], check["code"].replace("_", " "), check["message"]] for name, outline in outlines for check in outline["checks"]]
    checks += [[name, "", "coverage", f"{outline['coverage']['missing_words']:,} of {outline['coverage']['body_words']:,} body words aren't in any row"]
               for name, outline in outlines if outline["coverage"] and outline["coverage"]["missing_words"]]
    checks += [[name, "", "no sections", "No numbered sections or clauses found — its fields are in the Original File export."] for name in without]
    write_table_sheet(wb.create_sheet("Checks"), title="Checks", subtitle="Reported for review; nothing was added or changed.",
                      columns=["Document", "Clause", "Check", "Detail"],
                      rows=checks or [["", "", "", "No missing clauses, numbering gaps or empty headings found."]], wide_columns={"Detail"})
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
