"""FAR Part HTML → one record per FAR article, DOM first.

Any FAR Part (Part 52's clauses and provisions, or a policy Part such as
Part 42's sections); the Part heading fixes which numbers are the Part's
own records.

The regulation's HTML (acquisition.gov / DITA output) nests one <article>
per FAR unit: the Part, each Subpart, and every section / provision /
clause, each opened by a numbered heading. A record is the article's own
heading plus its own body — child articles are separate records.

Inside a record, text is rendered block by block in document order and is
never rewritten (whitespace is normalized; words, punctuation, "e.g." and
paragraph markers are kept). Nested (a)/(1)/(i)/(A) paragraphs stay inside
their record. A structural Alternate is a paragraph that STARTS with
"Alternate <Roman> (<date>)." — narrative mentions such as
"(v) Alternate IV (Jan 2025) of 52.219-9" are ignored. Embedded
"52.xxx-x" references are indexed, never turned into records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from lxml import html as lxml_html

EXTRACTOR_VERSION = 2

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_CONTAINERS = {"div", "section", "ul", "ol", "dl", "blockquote", "tbody", "thead", "tfoot", "figure", "main", "form", "fieldset", "center"}
_SKIP = {"script", "style", "noscript", "template", "nav", "article"}
_TABLE_SEPARATOR = " | "

# "52.204-6", "42.1101", "Subpart 42.1", "Part 42" at the start of a heading.
_NUMBER = re.compile(r"^(?P<number>(?:Part|Subpart)\s+\d{1,2}(?:\.\d+)?|\d{1,2}\.\d{3,4}(?:-\d+)?)(?![\d-])")
_CLAUSE_NUMBER = re.compile(r"^\d{1,2}\.\d{3,4}(?:-\d+)?$")
_SUBPART = re.compile(r"^Subpart\s+\d{1,2}\.\d+$")
_PART = re.compile(r"^Part\s+\d{1,2}$")
_TITLE_LEAD = re.compile(r"^[\s\-‐-―:]+")
_RESERVED = re.compile(r"^\[\s*Reserved\s*\]$", re.I)

_MONTH = r"(?i:(?:Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)[a-z]*)\.?"
_HEADING_DATE = re.compile(r"\(\s*(?P<month>" + _MONTH + r")\s*(?P<year>\d{4})\s*\)\s*$")
_ALTERNATE = re.compile(
    r"^Alternate\s+(?P<roman>[IVX]+)\s*\(\s*(?P<month>" + _MONTH + r")\s*(?P<year>\d{4})\s*\)\s*\.\s*"
)
# "Alternate I [Reserved]": a structural placeholder with no text of its own.
_RESERVED_ALTERNATE = re.compile(r"^Alternate\s+(?P<roman>[IVX]+)\s*\[\s*Reserved\s*\]\s*\.?$", re.I)
# Narrative mention of an alternate (for QA counts only — never a record).
_ALTERNATE_MENTION = re.compile(r"\bAlternate\s+[IVX]+\s*\(\s*" + _MONTH + r"\s*\d{4}\s*\)")
_PRESCRIPTION = re.compile(r"^As\s+prescribed\b", re.I)
_PRESCRIPTION_REFERENCE = re.compile(
    r"^As\s+prescribed\s+(?:in|at|by)\s+(?:FAR\s+)?(?:(?:sub)?part\s+|section\s+)?(?P<ref>\d+\.\d+(?:-\d+)*)",
    re.I,
)
_INSERT_KIND = re.compile(r"\b(?:insert|use)\b[^:]*?\b(?P<kind>provision|clause)\b", re.I)
_END_MARKER = re.compile(r"^\(End of (?P<kind>provision|clause)\)$", re.I)
_FAR_REFERENCE = re.compile(r"(?<![\d.])52\.\d{3}(?:-\d+)?(?!\d)(?!-\d)")
# Outside Part 52 every FAR section is a cross-reference ("see 37.104").
_ANY_FAR_REFERENCE = re.compile(r"(?<![\d.$])\d{1,2}\.\d{3,4}(?:-\d+)?(?!\d)(?!-\d)")


def part_number(number: str | None) -> str | None:
    """"52" for "52.204-6", "Subpart 52.1" or "Part 52"."""

    match = re.search(r"(\d{1,2})(?:\.|$)", number or "")
    return match.group(1) if match else None


def reference_pattern(part: str | None) -> re.Pattern:
    return _FAR_REFERENCE if part in (None, "52") else _ANY_FAR_REFERENCE


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("­", "-")).strip()


def month_year(month: str, year: str) -> str:
    return f"{month.rstrip('.').capitalize()} {year}"


@dataclass
class Block:
    text: str
    element: object
    # Characters this block adds that are not source text (table cell
    # separators) — excluded by the completeness check.
    added_chars: int = 0


@dataclass
class FarAlternate:
    code: str  # "Alternate I"
    roman: str
    date: str | None  # "Oct 1997"; None for a reserved alternate
    heading: str  # "Alternate I (Oct 1997)" as it appears (normalized spacing)
    instruction: str  # the heading paragraph after the heading
    prescription_reference: str | None
    text: str  # complete alternate text, heading paragraph first
    element_id: str | None
    dom_path: str
    embedded_references: list[str] = field(default_factory=list)
    reserved: bool = False


@dataclass
class FarSourceRecord:
    sequence: int
    far_number: str
    kind: str  # "subpart" | "reserved" | "section"
    heading_text: str  # the heading exactly (normalized whitespace)
    title: str
    element_id: str | None
    dom_path: str
    heading_dom_path: str
    section_path: list[str]
    subpart: str | None
    subpart_title: str | None
    grouped_text: str  # every block of the record, alternates included
    basic_text: str  # the record without its structural alternates
    official_heading: str | None = None
    official_heading_dom_path: str | None = None
    revision_date: str | None = None
    prescription: str | None = None
    prescription_dom_path: str | None = None
    prescription_reference: str | None = None
    clause_type: str | None = None  # "Clause" | "Provision"
    clause_type_evidence: str | None = None
    alternates: list[FarAlternate] = field(default_factory=list)
    embedded_references: list[str] = field(default_factory=list)  # grouped text
    basic_embedded_references: list[str] = field(default_factory=list)
    narrative_alternate_mentions: int = 0
    # Non-whitespace source characters vs. rendered characters — equal
    # when nothing was dropped.
    source_char_count: int = 0
    rendered_char_count: int = 0
    issues: list[str] = field(default_factory=list)
    # PDF sources: the page the heading is on and the record's last page.
    page: int | None = None
    end_page: int | None = None

    @property
    def section_group(self) -> str | None:
        """"52.204" for "52.204-6" (the reference's SubID)."""

        if "-" in self.far_number and _CLAUSE_NUMBER.match(self.far_number):
            return self.far_number.split("-", 1)[0]
        return None

    @property
    def subsection(self) -> str | None:
        if self.kind == "subpart":
            return None
        return self.section_group or self.far_number


@dataclass
class FarExtraction:
    part_heading: str | None
    records: list[FarSourceRecord]
    article_count: int
    warnings: list[str] = field(default_factory=list)


def _tag(el) -> str:
    return el.tag.lower() if isinstance(el.tag, str) else ""


def _classes(el) -> set[str]:
    return set((el.get("class") or "").split())


def parse(raw: bytes):
    return lxml_html.document_fromstring(raw)


def _own_heading(article):
    for child in article:
        if _tag(child) in _HEADING_TAGS:
            return child
    return None


def _split_heading(heading) -> tuple[str | None, str]:
    text = clean(element_text(heading))
    number_el = heading.xpath(".//span[contains(concat(' ', normalize-space(@class), ' '), ' autonumber ')]")
    number = clean(number_el[0].text_content()) if number_el else None
    if number and text.startswith(number):
        rest = text[len(number):]
    else:
        match = _NUMBER.match(text)
        if not match:
            return None, text
        number, rest = match.group("number"), text[match.end():]
    number = clean(number)
    if not (_CLAUSE_NUMBER.match(number) or _SUBPART.match(number) or _PART.match(number)):
        return None, text
    title = _TITLE_LEAD.sub("", rest).strip()
    if title.endswith(".") and not title.endswith("..."):
        title = title[:-1].rstrip()
    return number, title


_INLINE_BLOCKS = {"p", "div", "li", "ul", "ol", "table", "tr", "section", "dl", "dt", "dd", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}
_DROPPED = {"script", "style", "noscript", "template"}


def element_text(el) -> str:
    """Readable text of one block: source line-wrapping inside a paragraph
    collapses to single spaces; <br> and nested blocks become line breaks.
    Characters are otherwise kept exactly."""

    parts: list[str] = []

    def walk(node):
        tag = _tag(node)
        if tag in _DROPPED or not tag:
            if node.tail:
                parts.append(node.tail)
            return
        if tag == "br":
            parts.append("\n")
        elif tag in _INLINE_BLOCKS:
            parts.append("\n")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
        if tag in _INLINE_BLOCKS:
            parts.append("\n")
        if node.tail:
            parts.append(node.tail)

    if el.text:
        parts.append(el.text)
    for child in el:
        walk(child)
    joined = "".join(p if p == "\n" else re.sub(r"\s+", " ", p) for p in parts)
    lines = [clean(line) for line in joined.split("\n")]
    return "\n".join(line for line in lines if line)


def _render(el, blocks: list[Block]) -> None:
    """Appends el's readable blocks in document order."""

    if el.text and el.text.strip():
        blocks.append(Block(clean(el.text), el))
    for child in el:
        tag = _tag(child)
        if tag and tag not in _SKIP:
            if tag == "table":
                for tr in child.xpath(".//tr"):
                    cells = [clean(element_text(c)) for c in tr if _tag(c) in ("td", "th")]
                    cells = [c for c in cells if c] or []
                    if cells:
                        blocks.append(
                            Block(_TABLE_SEPARATOR.join(cells), tr, added_chars=len(cells) - 1)
                        )
            elif tag in _CONTAINERS and any(_tag(g) in _CONTAINERS | {"p", "table", "li", "dt", "dd", "pre"} for g in child):
                _render(child, blocks)
            else:
                text = element_text(child)
                if text:
                    blocks.append(Block(text, child))
        if child.tail and child.tail.strip():
            blocks.append(Block(clean(child.tail), el))


def _nonspace(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _source_chars(el) -> int:
    """Non-whitespace characters of the element's own content (child
    articles excluded), as the DOM holds them."""

    total = 0
    if el.text:
        total += _nonspace(el.text)
    for child in el:
        tag = _tag(child)
        if tag and tag not in _SKIP:
            total += _nonspace(child.text_content())
        if child.tail:
            total += _nonspace(child.tail)
    return total


def _references(text: str, own: str) -> list[str]:
    seen: list[str] = []
    for match in reference_pattern(part_number(own)).finditer(text):
        ref = match.group(0)
        if ref != own and ref not in seen:
            seen.append(ref)
    return seen


def _container_of(el, body):
    """The nearest <section> between a block and the record body — an
    alternate owns the blocks of its section."""

    for ancestor in el.iterancestors():
        if ancestor is body:
            return body
        if _tag(ancestor) == "section":
            return ancestor
    return body


def _is_descendant(el, container) -> bool:
    return any(a is container for a in el.iterancestors())


def _record(article, tree, sequence: int, number: str, title: str, heading, trail: list[str], subpart: tuple[str, str] | None) -> FarSourceRecord:
    heading_text = clean(element_text(heading))
    if _SUBPART.match(number):
        kind = "subpart"
    elif _RESERVED.match(title):
        kind = "reserved"
    else:
        kind = "section"

    bodies = [c for c in article if _tag(c) not in _HEADING_TAGS and _tag(c) not in _SKIP]
    blocks: list[Block] = []
    source_chars = 0
    for body in bodies:
        _render(body, blocks)
        source_chars += _source_chars(body) if _tag(body) in _CONTAINERS else _nonspace(body.text_content())
    for child in article:
        if child.tail and child.tail.strip():
            blocks.append(Block(clean(child.tail), article))
            source_chars += _nonspace(child.tail)

    # Split structural alternates out of the basic record.
    basic: list[Block] = []
    alternates: list[tuple[re.Match, Block, object, list[Block]]] = []
    current = None
    body_el = bodies[0] if bodies else article
    for block in blocks:
        match = (
            (_ALTERNATE.match(block.text) or _RESERVED_ALTERNATE.match(block.text))
            if _tag(block.element) == "p"
            else None
        )
        if match:
            current = (match, block, _container_of(block.element, body_el), [block])
            alternates.append(current)
            continue
        if current is not None and current[2] is not body_el and not _is_descendant(block.element, current[2]):
            current = None
        if current is not None:
            current[3].append(block)
        else:
            basic.append(block)

    record = FarSourceRecord(
        sequence=sequence,
        far_number=number,
        kind=kind,
        heading_text=heading_text,
        title=title,
        element_id=article.get("id"),
        dom_path=tree.getpath(article),
        heading_dom_path=tree.getpath(heading),
        section_path=[*trail, heading_text],
        subpart=number if kind == "subpart" else (subpart[0] if subpart else None),
        subpart_title=title if kind == "subpart" else (subpart[1] if subpart else None),
        grouped_text="\n".join(b.text for b in blocks),
        basic_text="\n".join(b.text for b in basic),
        source_char_count=source_chars,
        rendered_char_count=sum(_nonspace(b.text) - b.added_chars for b in blocks),
    )
    if kind == "subpart":
        return record

    for block in basic:
        if "Ctr_SmCaps" in _classes(block.element):
            record.official_heading = block.text
            record.official_heading_dom_path = tree.getpath(block.element)
            date = _HEADING_DATE.search(block.text)
            if date:
                record.revision_date = month_year(date.group("month"), date.group("year"))
            break
    if basic and _PRESCRIPTION.match(basic[0].text):
        record.prescription = basic[0].text
        record.prescription_dom_path = tree.getpath(basic[0].element)
        ref = _PRESCRIPTION_REFERENCE.match(basic[0].text)
        record.prescription_reference = ref.group("ref") if ref else None
        kind_match = _INSERT_KIND.search(basic[0].text)
        if kind_match:
            record.clause_type = kind_match.group("kind").capitalize()
            record.clause_type_evidence = basic[0].text
    if record.clause_type is None:
        for block in basic:
            end = _END_MARKER.match(block.text)
            if end:
                record.clause_type = end.group("kind").capitalize()
                record.clause_type_evidence = block.text
                break

    for match, heading_block, _container, alt_blocks in alternates:
        roman = match.group("roman")
        reserved = match.re is _RESERVED_ALTERNATE
        instruction = "" if reserved else heading_block.text[match.end():].strip()
        ref = _PRESCRIPTION_REFERENCE.match(instruction)
        text = "\n".join(b.text for b in alt_blocks)
        record.alternates.append(
            FarAlternate(
                code=f"Alternate {roman}",
                roman=roman,
                date=None if reserved else month_year(match.group("month"), match.group("year")),
                reserved=reserved,
                heading=heading_block.text
                if reserved
                else heading_block.text[: match.end()].strip().rstrip(".").strip(),
                instruction=instruction,
                prescription_reference=ref.group("ref") if ref else None,
                text=text,
                element_id=heading_block.element.get("id"),
                dom_path=tree.getpath(heading_block.element),
                embedded_references=_references(text, number),
            )
        )

    record.embedded_references = _references(record.grouped_text, number)
    record.basic_embedded_references = _references(record.basic_text, number)
    structural = {a.dom_path for a in record.alternates}
    record.narrative_alternate_mentions = sum(
        len(_ALTERNATE_MENTION.findall(b.text))
        for b in blocks
        if tree.getpath(b.element) not in structural
    )

    if record.official_heading and _HEADING_DATE.search(record.official_heading) is None:
        record.issues.append("Official heading has no recognizable (Month YYYY) date.")
    if record.prescription and not record.prescription_reference:
        record.issues.append("Prescription found but its FAR reference could not be read.")
    if kind == "section" and not record.grouped_text:
        record.issues.append("Section heading has no body text.")
    return record


_NO_BODY = "Section heading has no body text."


def clear_parent_no_body(records: list[FarSourceRecord]) -> None:
    """A section whose text is all in its subsections (16.202 → 16.202-1,
    16.202-2) has no body of its own by design — not an issue."""

    numbers = {r.far_number for r in records}
    for record in records:
        if _NO_BODY in record.issues and any(n.startswith(record.far_number + "-") for n in numbers):
            record.issues.remove(_NO_BODY)


def _expected_number(element_id: str | None) -> str | None:
    """"FAR_52_204_6" → "52.204-6"; "FAR_Subpart_52_1" → "Subpart 52.1"."""

    if not element_id:
        return None
    match = re.fullmatch(r"FAR_(Subpart_)?(\d{1,2})_(\d+)(?:_(\d+))?", element_id)
    if not match:
        return None
    part = match.group(2)
    if match.group(1):
        return f"Subpart {part}.{match.group(3)}"
    return f"{part}.{match.group(3)}" + (f"-{match.group(4)}" if match.group(4) else "")


def extract_far(raw: bytes) -> FarExtraction:
    root = parse(raw)
    tree = root.getroottree()
    part_heading: str | None = None
    records: list[FarSourceRecord] = []
    warnings: list[str] = []
    articles = root.xpath("//article")
    subpart: tuple[str, str] | None = None
    part_trail: list[str] = []
    part: str | None = None

    for article in articles:
        heading = _own_heading(article)
        if heading is None:
            continue
        number, title = _split_heading(heading)
        if number is None:
            continue
        if _PART.match(number):
            if part_heading is None:
                part_heading = clean(element_text(heading))
                part_trail = [part_heading]
                part = part_number(number)
            continue
        # Only the Part's own numbers are its records (a heading quoting
        # another Part's section is not).
        part = part or part_number(number)
        if part_number(number) != part:
            continue
        subpart_ancestor = next(
            (
                a
                for a in article.iterancestors("article")
                if (h := _own_heading(a)) is not None and _SUBPART.match(_split_heading(h)[0] or "")
            ),
            None,
        )
        if _SUBPART.match(number):
            subpart = (number, title)
            trail = part_trail
        elif subpart_ancestor is not None:
            h = _own_heading(subpart_ancestor)
            subpart = (_split_heading(h)[0], _split_heading(h)[1])
            trail = [*part_trail, clean(element_text(h))]
        else:
            subpart = None
            trail = part_trail
        record = _record(article, tree, len(records) + 1, number, title, heading, trail, subpart if not _SUBPART.match(number) else None)
        expected = _expected_number(article.get("id"))
        if expected and expected != number:
            record.issues.append(f"Heading number {number} does not match element id {article.get('id')}.")
        records.append(record)

    clear_parent_no_body(records)
    seen: dict[str, int] = {}
    for record in records:
        seen[record.far_number] = seen.get(record.far_number, 0) + 1
    for number, count in seen.items():
        if count > 1:
            warnings.append(f"FAR number {number} heads {count} articles.")
            for record in records:
                if record.far_number == number:
                    record.issues.append(f"Duplicate FAR number ({count} articles).")
    return FarExtraction(
        part_heading=part_heading,
        records=records,
        # FAR-headed articles: every record plus the Part title article.
        article_count=len(records) + (1 if part_heading else 0),
        warnings=warnings,
    )


@dataclass(frozen=True)
class FarRecognition:
    score: float
    reasons: list[str]


def score_far_structure(
    part: str | None, subparts: int, numbered: int, prescribed: int, parent_topic: bool
) -> FarRecognition:
    """A FAR Part heading, Subpart N.x headings and many numbered FAR
    section headings of that Part, plus either clause prescriptions or the
    regulation's own "Parent topic: Federal Acquisition Regulation"."""

    reasons: list[str] = []
    score = 0.0
    if part:
        score += 0.25
        reasons.append(f"Part {part} heading")
    if subparts >= 2:
        score += 0.25
        reasons.append(f"{subparts} Subpart {part or 'N'}.x headings")
    if numbered >= 10:
        score += 0.3
        reasons.append(f"{numbered} numbered FAR section/clause headings")
    if prescribed >= 10:
        score += 0.2
        reasons.append(f"{prescribed} 'As prescribed in' prescriptions")
    elif parent_topic:
        score += 0.2
        reasons.append("'Parent topic: Federal Acquisition Regulation'")
    return FarRecognition(round(score, 2), reasons or ["no FAR Part structure"])


_PARENT_TOPIC = re.compile(r"Parent topic:\s*Federal Acquisition Regulation", re.I)


# Cached by content: one run asks of the same file several times, and a
# full Part is megabytes of DOM to parse.
@lru_cache(maxsize=8)
def recognize_far_part(raw: bytes) -> FarRecognition:
    """Structural evidence that a document IS a FAR Part (not a contract
    that cites FAR clauses): a Part heading, Subpart headings and many
    numbered FAR headings of that Part, each opening its own section. The
    filename is never consulted."""

    root = parse(raw)
    part: str | None = None
    subparts = numbered = prescribed = 0
    numbers: list[str] = []
    for heading in root.xpath("//h1|//h2|//h3|//h4|//h5|//h6"):
        number, _title = _split_heading(heading)
        if number is None:
            continue
        if _PART.match(number):
            part = part or part_number(number)
        else:
            numbers.append(number)
    part_of = part or (part_number(numbers[0]) if numbers else None)
    for number in numbers:
        if part_number(number) != part_of:
            continue
        if _SUBPART.match(number):
            subparts += 1
        else:
            numbered += 1
    for p in root.xpath("//p"):
        if _PRESCRIPTION.match(clean(p.text_content())):
            prescribed += 1
    return score_far_structure(part, subparts, numbered, prescribed, bool(_PARENT_TOPIC.search(root.text_content())))


# Kept for callers of the Part 52 name.
recognize_far_part_52 = recognize_far_part
