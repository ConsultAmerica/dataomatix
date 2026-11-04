"""The text of a document section, found from a table-of-contents entry.

A contents entry ("B.1 Background .......... 11") only gives a heading and
a page number. This finds the heading where it is printed in the body and
returns the text under it, up to the next numbered heading (or the next
contents entry), read from the stored page text — the same text the Full
Text view shows. Nothing is rewritten or summarised; the extracted values
stay as they are. A heading that can't be found is reported as not found.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# A line that starts a section: "B.1.2 Contract Type", "C.3 Scope", "H.12 …",
# "Section C - Description", "PART II", "ARTICLE 4".
_HEADING = re.compile(
    r"^\s*(?:[A-Z]{1,2}\.\d+(?:\.\d+)*\.?\s+\S|Section\s+[A-Z]\b|PART\s+[IVX]+\b|ARTICLE\s+\d+\b|\d+(?:\.\d+)+\.?\s+[A-Z])"
)
_LEADERS = re.compile(r"(?:\s*[.·…_]\s*){4,}")
_RUNNING_HEAD = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.I)
# A page of a table of contents: many leader lines.
_CONTENTS_LINE = re.compile(r"[.·…]{6,}\s*\d{1,4}\s*$")
MAX_CHARS = 60_000


@dataclass(frozen=True)
class PageText:
    number: int
    label: str | None
    text: str


def _norm(text: str) -> str:
    text = _LEADERS.sub(" ", text)
    text = re.sub(r"[\s ]+", " ", text).strip().lower()
    return text.rstrip(" .:-–—")


def _number_token(heading: str) -> str | None:
    match = re.match(r"^\s*([A-Z]{1,2}\.\d+(?:\.\d+)*|Section\s+[A-Z]|PART\s+[IVX]+|ARTICLE\s+\d+|\d+(?:\.\d+)+)\b", heading, re.I)
    return _norm(match.group(1)) if match else None


def _is_contents_page(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    return sum(1 for line in lines if _CONTENTS_LINE.search(line)) >= 5


def _heading_matches(line: str, heading: str) -> bool:
    line_n, heading_n = _norm(line), _norm(heading)
    if not line_n or not heading_n:
        return False
    if line_n.startswith(heading_n) or heading_n.startswith(line_n) and len(line_n) >= 6:
        return True
    # Same number with a title that starts the same ("B.1 Background" ~ "B.1 BACKGROUND:").
    number = _number_token(heading)
    if number and _number_token(line) == number:
        # Titles compared by letters and digits only: a dash or colon the
        # contents line dropped ("Section 1 – General") doesn't matter.
        rest_h = re.sub(r"[^a-z0-9]+", "", heading_n[len(number):])
        rest_l = re.sub(r"[^a-z0-9]+", "", line_n[len(number):])
        return not rest_h or not rest_l or rest_l.startswith(rest_h[:12]) or rest_h.startswith(rest_l[:12])
    return False


def _section_key(heading: str) -> str | None:
    """"b.1" for "B.1 Background", "c" for "Section C - …", "ii" for "PART II"."""

    number = _number_token(heading)
    if not number:
        return None
    return re.sub(r"^(section|part|article)\s+", "", number)


def _is_subsection(line: str, key: str | None) -> bool:
    other = _section_key(line)
    return bool(key and other and other != key and other.startswith(key + "."))


@dataclass
class SectionIndex:
    """The body pages split into lines once, with which lines are headings,
    so many entries of one contents page are looked up in one pass each."""

    pages: list[PageText]
    lines: list[list[str]]
    normalized: list[list[str]]
    headings: list[list[bool]]


def prepare(pages: Iterable[PageText]) -> SectionIndex:
    body = [page for page in sorted(pages, key=lambda page: page.number) if not _is_contents_page(page.text)]
    lines = [page.text.splitlines() for page in body]
    return SectionIndex(
        pages=body,
        lines=lines,
        normalized=[[_norm(line) for line in page_lines] for page_lines in lines],
        headings=[[bool(_HEADING.match(line)) for line in page_lines] for page_lines in lines],
    )


# Own text shorter than this is a heading with only subsections under it.
_THIN = 80


def find_section(pages: Iterable[PageText] | SectionIndex, heading: str, *, page_hint: int | None = None,
                 next_headings: Iterable[str] = (), include_subsections: bool | None = None) -> dict:
    """The body text under `heading`, or found=False with the reason. With
    include_subsections None, subsections are included only when the
    section has (almost) no text of its own."""

    index = pages if isinstance(pages, SectionIndex) else prepare(pages)
    if include_subsections is None:
        own = find_section(index, heading, page_hint=page_hint, next_headings=next_headings, include_subsections=False)
        if not own["found"] or own["characters"] >= _THIN:
            return own
        return find_section(index, heading, page_hint=page_hint, next_headings=next_headings, include_subsections=True)
    key = _section_key(heading)
    body = index.pages
    prefix = _norm(heading)[:20]
    candidates: list[tuple[int, int]] = []  # (page index in body, line index)
    for page_index, page_lines in enumerate(index.lines):
        for line_index, line in enumerate(page_lines):
            if index.headings[page_index][line_index] or (prefix and index.normalized[page_index][line_index].startswith(prefix)):
                if _heading_matches(line, heading):
                    candidates.append((page_index, line_index))
    if not candidates:
        return {"heading": heading, "found": False, "reason": "The heading wasn't found in the document's text."}

    def distance(candidate: tuple[int, int]) -> tuple[int, int]:
        page = body[candidate[0]]
        if page_hint is None:
            return (0, candidate[0])
        printed = int(page.label) if page.label and page.label.isdigit() else page.number
        # The printed page number first; pages after it before pages before it.
        return (min(abs(printed - page_hint), abs(page.number - page_hint)), 0 if page.number >= page_hint else 1)

    start_page, start_line = min(candidates, key=distance)
    stops = [heading_ for heading_ in next_headings if heading_ and _norm(heading_) != _norm(heading)]
    lines_out: list[str] = []
    end_page = body[start_page].number
    finished = False
    for page_index in range(start_page, len(body)):
        for line_index, line in enumerate(index.lines[page_index]):
            if page_index == start_page and line_index <= start_line:
                continue
            if index.headings[page_index][line_index]:
                if include_subsections and _is_subsection(line, key):
                    lines_out.append(line)
                    end_page = body[page_index].number
                    continue
                finished = True
                break
            if not include_subsections and stops and any(_heading_matches(line, stop) for stop in stops):
                finished = True
                break
            if _RUNNING_HEAD.match(line):
                continue
            lines_out.append(line)
            if line.strip():
                end_page = body[page_index].number
        if finished:
            break
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in lines_out)).strip()
    truncated = len(text) > MAX_CHARS
    return {
        "heading": heading,
        "found": True,
        "page_start": body[start_page].number,
        "page_end": end_page,
        "printed_heading": index.lines[start_page][start_line].strip(),
        "text": text[:MAX_CHARS],
        "truncated": truncated,
        "characters": len(text),
        "includes_subsections": include_subsections,
    }


def contents_heading(label: str, value: str | None) -> tuple[str, int | None]:
    """The heading and printed page of a contents entry: "B.1 Background" with
    "11"; or "Section C" with "Description/… ......... 19"."""

    value = (value or "").strip()
    match = re.search(r"(\d{1,4})\s*$", value)
    page = int(match.group(1)) if match else None
    title = _LEADERS.sub(" ", value[: match.start()] if match else value).strip()
    heading = f"{label.strip()} {title}".strip() if title and not title.isdigit() else label.strip()
    return heading, page
