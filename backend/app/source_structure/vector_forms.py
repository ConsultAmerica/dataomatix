"""Drawn forms read box by box.

A form printed from vector graphics — an SF1442, a flattened SF33 — has no
fill-in widgets: its boxes are ruled rectangles, each a small printed
caption over the value typed into it. The table finder sees one irregular
grid and rejects it, and column alignment then mistakes rows of boxes for
tables. Here the page's own rules give the boxes, with the frame/divider
logic of a scanned form (raster_tables.RasterGrid.form_boxes); each box is
cut again by any rule that crosses it, and its words are split into
caption (small print) and value (typed text) word by word:

- a box's leading caption is its item ("7. ISSUED BY"); another caption in
  the same box ("CODE") is a sub-field of that item with the value beside
  or under it;
- a lettered box ("A. NAME") in the row of a numbered box that holds no
  value of its own ("10. FOR INFORMATION CALL:") is that item's sub-item;
- rows of boxes ruled alike, with no numbered caption among them, are a
  table inside the form (a table of contents), its side-by-side halves
  stacked in reading order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.source_structure.models import FieldCandidate, StructuredRegion, TableCandidate
from app.source_structure.pdf_structure import (
    BBox,
    Line,
    Segment,
    Word,
    _Ids,
    _field,
    _table_from_grid,
    _union,
)
from app.source_structure.form_geometry import NOT_SELECTED, SELECTED, UNRECOGNIZED
from app.source_structure.raster_tables import RasterGrid
from app.source_structure.text_shapes import normalize_space

# A stroke or filled bar thinner than this (points) is a rule.
_THIN = 1.5
# Rules this close (points) are one rule; a box narrower or shorter is none.
_NEAR = 2.0
_MIN_BOX = 6.0
# A printed tick box is a square no larger than this (points); a box
# narrower than a sliver holds no field of its own.
_CHECKBOX = 16.0
_SLIVER = 15.0
# A drawn form numbers at least this many of its boxes ("1.", "12B.").
_MIN_NUMBERED = 3
# Words further apart than this (points) on a line are separate runs.
_RUN_GAP = 8.0
# Typed text set at least this much larger than the form's captions (a
# flattened SF33 types at 9.4 pt over 5.4 pt captions; some captions are
# set a little larger, 6.2 pt).
_TYPED = 1.25
# A lower line in a one-size box that is printed, not typed: a
# parenthetical ("(Include area code)") or a caption ending in ":" ("TEL:").
_PRINTED_LINE = re.compile(r"^\([A-Za-z]|^[^\d]{1,40}:$|\((?:[A-Za-z]+\s){1,6}[A-Za-z]+\)$")
# A full stop that doesn't end an option: "U.S.C.", "No.", "(a)."
_ABBREVIATION = re.compile(r"^\(?(?:[A-Za-z]{1,3}\.){2,}$|^(?:No|Nos|Inc|Co|Ltd|St|Sec|Ch)\.$|^\(?[A-Za-z0-9]{1,3}[.)]$")
# An option that is a numbered item itself: "29. AWARD" (never "10 U.S.C.").
_OWN_ITEM = re.compile(r"^(?P<code>\d{1,3}[A-Z]?)\.\s+(?P<name>\S.*)$")
# A printed instruction closing an option's caption.
_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)?\s*$")
# A selection mark typed into a box.
_MARKS = {"X", "x", "✓", "✔", "☒"}
# "7. ISSUED BY", "12B. CALENDAR DAYS", "12 A. THE CONTRACTOR …"
_ITEM = re.compile(r"^(?P<code>\d{1,3}(?:\s?[A-Z])?)[.)]?\s+(?P<name>\S.*)$")
# "A. NAME", "B. TELEPHONE NO."
_LETTER = re.compile(r"^(?P<code>[A-Z])[.)]\s+(?P<name>\S.*)$")


def vector_rules(page) -> tuple[list[tuple[float, float, float, float]], list[tuple[float, float, float]]]:
    """(horizontal rules (x0, y, x1, y), vertical rules (x, y0, y1)) drawn
    on the page: stroked lines, thin filled bars and stroked rectangles'
    sides, with collinear pieces joined."""

    h: list[tuple[float, float, float]] = []
    v: list[tuple[float, float, float]] = []
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001 - a page without readable drawings has no rules
        return [], []
    for drawing in drawings:
        for item in drawing.get("items") or []:
            if item[0] == "l":
                p, q = item[1], item[2]
                if abs(p.y - q.y) <= 0.5 and abs(p.x - q.x) > _MIN_BOX:
                    h.append((p.y, min(p.x, q.x), max(p.x, q.x)))
                elif abs(p.x - q.x) <= 0.5 and abs(p.y - q.y) > _MIN_BOX:
                    v.append((p.x, min(p.y, q.y), max(p.y, q.y)))
            elif item[0] == "re":
                r = item[1]
                if r.height <= _THIN and r.width > _MIN_BOX:
                    h.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
                elif r.width <= _THIN and r.height > _MIN_BOX:
                    v.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                elif _checkbox(r):
                    continue  # a printed tick box beside an option, not a rule
                elif r.width > _MIN_BOX and r.height > _MIN_BOX and drawing.get("color") is not None:
                    h += [(r.y0, r.x0, r.x1), (r.y1, r.x0, r.x1)]
                    v += [(r.x0, r.y0, r.y1), (r.x1, r.y0, r.y1)]
    rows = [(x0, y, x1, y) for y, x0, x1 in _join(h)]
    return rows, _join(v)


def _checkbox(rect) -> bool:
    """A small, near-square rectangle: the box an option is ticked in."""

    w, h = rect.width, rect.height
    return 3 <= w <= _CHECKBOX and 3 <= h <= _CHECKBOX and max(w, h) <= 1.6 * min(w, h)


def checkboxes(page) -> list[BBox]:
    """The page's printed tick boxes (their squares)."""

    found = []
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return found
    for drawing in drawings:
        for item in drawing.get("items") or []:
            if item[0] == "re" and _checkbox(item[1]):
                r = item[1]
                rect = (r.x0, r.y0, r.x1, r.y1)
                # The same square drawn twice (fill, then stroke) is one box.
                if not any(all(abs(a - b) <= 1 for a, b in zip(rect, other)) for other in found):
                    found.append(rect)
    return found


def _join(rules: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """Collinear pieces (same position, touching or overlapping) as one rule."""

    out: list[list[float]] = []
    for at, start, end in sorted(rules):
        last = out[-1] if out else None
        if last and abs(last[0] - at) <= 0.5 and start <= last[2] + _NEAR:
            last[2] = max(last[2], end)
        else:
            out.append([at, start, end])
    return [tuple(rule) for rule in out]


def form_boxes(page, h=None, v=None) -> list[BBox] | None:
    """The page's ruled form boxes in reading order, or None when its rules
    form no form (none, or a table whose columns run through every row)."""

    if h is None or v is None:
        h, v = vector_rules(page)
    if len(h) < 3 or len(v) < 3:
        return None
    grid = RasterGrid(
        columns=sorted({round(x, 1) for x, _, _ in v}),
        top=min(y for _, y, _, _ in h),
        bottom=max(y for _, y, _, _ in h),
        row_rules=h,
        rule_spans=v,
    )
    boxes = grid.form_boxes()
    if not boxes:
        return None
    cuts = _merge_slivers([cut for box in boxes for cut in _cut(box, h, v)])
    return sorted(cuts, key=lambda b: (round(b[1]), b[0]))


def _stack_slivers(boxes: list[BBox]) -> list[BBox]:
    """Narrow boxes stacked in one column (a column of tick squares) as one."""

    out: list[BBox] = []
    for box in sorted(boxes, key=lambda b: (round(b[0]), b[1])):
        last = out[-1] if out else None
        if (
            last is not None and box[2] - box[0] < _SLIVER and last[2] - last[0] < _SLIVER
            and abs(last[0] - box[0]) <= _NEAR and abs(last[2] - box[2]) <= _NEAR and abs(last[3] - box[1]) <= _NEAR
        ):
            out[-1] = (min(last[0], box[0]), last[1], max(last[2], box[2]), box[3])
        else:
            out.append(box)
    return out


def _merge_slivers(boxes: list[BBox]) -> list[BBox]:
    """A box too narrow to hold a field — the column of tick squares beside
    "SEALED BID / NEGOTIATED", the "2." printed left of its caption — is part
    of the box it sits against (the one to its right, else its left)."""

    boxes = _stack_slivers(list(boxes))
    while True:
        # Right to left: the tick column joins its options before the "2."
        # left of it joins the two.
        for sliver in sorted(boxes, key=lambda b: -b[0]):
            if sliver[2] - sliver[0] >= _SLIVER:
                continue
            others = [o for o in boxes if o is not sliver]
            if any(_inside(sliver, o) for o in others):
                boxes.remove(sliver)
                break

            def beside(o: BBox, edge: int) -> bool:
                touching = abs(o[0] - sliver[2]) <= _NEAR if edge == 0 else abs(o[2] - sliver[0]) <= _NEAR
                return touching and o[1] <= sliver[1] + _NEAR and o[3] >= sliver[3] - _NEAR

            target = next((o for o in others if beside(o, 0)), None) or next((o for o in others if beside(o, 2)), None)
            if target is None:
                continue
            boxes.remove(sliver)
            boxes[boxes.index(target)] = (min(target[0], sliver[0]), target[1], max(target[2], sliver[2]), target[3])
            break
        else:
            return boxes


def _cut(box: BBox, h, v, depth: int = 0) -> list[BBox]:
    """A box divided by every rule that crosses it from side to side
    (15 TELEPHONE over 16 REMITTANCE in one column; 30A over 30B)."""

    x0, y0, x1, y1 = box
    if depth > 8:
        return [box]
    for rx0, y, rx1, _ in sorted(h, key=lambda r: r[1]):
        if y0 + _MIN_BOX < y < y1 - _MIN_BOX and rx0 <= x0 + _NEAR and rx1 >= x1 - _NEAR:
            return _cut((x0, y0, x1, y), h, v, depth + 1) + _cut((x0, y, x1, y1), h, v, depth + 1)
    for x, ry0, ry1 in sorted(v):
        if x0 + _MIN_BOX < x < x1 - _MIN_BOX and ry0 <= y0 + _NEAR and ry1 >= y1 - _NEAR:
            return _cut((x0, y0, x, y1), h, v, depth + 1) + _cut((x, y0, x1, y1), h, v, depth + 1)
    return [box]


# --- reading one box -------------------------------------------------------------------------


@dataclass
class _Run:
    """Consecutive words of one kind (caption or value) on one line."""

    words: list[Word]
    caption: bool
    line: int

    @property
    def text(self) -> str:
        return normalize_space(" ".join(w.text for w in self.words))

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def bbox(self) -> BBox:
        return _union([(w.x0, w.y0, w.x1, w.y1) for w in self.words])


@dataclass
class _Caption:
    run: _Run
    values: list[_Run] = field(default_factory=list)
    extra: list[_Run] = field(default_factory=list)  # wrapped / parenthetical caption text

    @property
    def text(self) -> str:
        return normalize_space(" ".join([self.run.text] + [r.text for r in self.extra]))

    @property
    def value(self) -> str:
        """Typed lines in order; two lines set close together stay two lines
        (an address's name and its "Attn" line)."""

        words = sorted((w for run in self.values for w in run.words), key=lambda w: w.cy)
        lines: list[list[Word]] = []
        for w in words:
            if lines and abs(lines[-1][0].cy - w.cy) <= 0.4 * (w.y1 - w.y0):
                lines[-1].append(w)
            else:
                lines.append([w])
        return "\n".join(normalize_space(" ".join(w.text for w in sorted(line, key=lambda w: w.x0))) for line in lines)


@dataclass
class _Box:
    rect: BBox
    head: _Caption | None
    subs: list[_Caption]
    segments: list[Segment]
    loose: list[_Run] = field(default_factory=list)  # values with no caption at all

    @property
    def item(self) -> re.Match | None:
        return _ITEM.match(self.head.text) if self.head else None

    @property
    def letter(self) -> re.Match | None:
        return _LETTER.match(self.head.text) if self.head else None


def _typed_word(text: str, position: int) -> bool:
    """On a caption line of a one-size box: a word typed into the box (an
    identifier, an amount, a date, a mark), not the caption's own words —
    its leading item number ("1.", "12", "12B.") is printed."""

    if text in _MARKS:
        return True
    if position == 0 and re.match(r"^\d{1,3}[A-Z]?[.)]?$", text):
        return False
    return bool(re.search(r"\d", text)) and not re.match(r"^\(?[A-Z][.)]$", text)


def _rows_in(lines: list[Line], box: BBox, taken: frozenset[int] = frozenset()) -> list[tuple[int, list[Word], list[Segment]]]:
    """(line index, the line's words inside the box, their segments), top to
    bottom: by each word's own centre — one run of text can cross a rule.
    `taken`: words already read as a selection's option or mark (by id)."""

    bx0, by0, bx1, by1 = box
    out = []
    for index, line in enumerate(lines):
        words, segments = [], []
        for seg in line.segments:
            if seg.used:
                continue
            inside = [
                w for w in seg.words
                if id(w) not in taken and bx0 - 1 <= (w.x0 + w.x1) / 2 <= bx1 + 1 and by0 - 1 <= w.cy <= by1 + 1
            ]
            if inside:
                words += inside
                segments.append(seg)
        if words:
            out.append((index, sorted(words, key=lambda w: w.x0), segments))
    return out


def page_sizes(lines: list[Line], rects: list[BBox]) -> tuple[float, bool]:
    """(caption size, whether typed values are set larger) for the page's
    form: the caption size is the usual size of the boxes' first words."""

    firsts, sizes = [], []
    for rect in rects:
        rows = _rows_in(lines, rect)
        if rows:
            firsts.append(rows[0][1][0].size)
            sizes += [w.size for _, ws, _ in rows for w in ws]
    if not firsts:
        return 0.0, False
    caption = sorted(firsts)[len(firsts) // 2]
    larger = sum(1 for size in sizes if size > _TYPED * caption)
    return caption, larger >= max(3, 0.05 * len(sizes))


def _read(lines: list[Line], rect: BBox, caption_size: float, sized: bool, taken: frozenset[int] = frozenset()) -> _Box | None:
    """A box's captions and values. Where typed values are set larger than
    the form's captions (a flattened SF33), size tells them apart; where
    one size is used throughout (an SF1442), position does."""

    rows = _rows_in(lines, rect, taken)
    if not rows:
        return None
    first_line = rows[0][0]
    runs: list[_Run] = []
    open_parens = 0  # in the printed caption so far
    for line_index, words, _ in rows:
        line_text = normalize_space(" ".join(w.text for w in words))
        printed_line = bool(open_parens > 0 or _PRINTED_LINE.search(line_text) or _LETTER.match(line_text))
        # On the caption line, typed words come last ("CODE  N40192"); a
        # number inside the caption's sentence ("ITEM 28 OR 29") is printed.
        typed_from = len(words)
        while typed_from > 1 and _typed_word(words[typed_from - 1].text, typed_from - 1):
            typed_from -= 1
        for position, w in enumerate(words):
            if w.text in _MARKS:
                is_caption = False
            elif sized:
                is_caption = w.size <= _TYPED * caption_size
            elif line_index == first_line:
                is_caption = position < typed_from and w.text not in _MARKS
            else:
                is_caption = printed_line
            closed = bool(runs) and runs[-1].caption and open_parens == 0 and runs[-1].words[-1].text.endswith((")", ":"))
            if is_caption:
                open_parens += w.text.count("(") - w.text.count(")")
            last = runs[-1] if runs else None
            new_caption = is_caption and closed and w.text[:1].isupper()
            if last and last.line == line_index and last.caption == is_caption and w.x0 - last.x1 < _RUN_GAP and not new_caption:
                last.words.append(w)
            else:
                runs.append(_Run([w], is_caption, line_index))
    captions = [r for r in runs if r.caption]
    values = [r for r in runs if not r.caption]
    box = _Box(rect=rect, head=None, subs=[], segments=[s for _, _, segs in rows for s in segs])
    if not captions:
        box.loose = values
        return box
    head = _Caption(captions[0])
    box.head = head
    for run in captions[1:]:
        previous = box.subs[-1] if box.subs else head
        prev_line = (previous.extra or [previous.run])[-1].line
        wraps = (
            run.text.startswith("(")
            or (run.line == prev_line + 1 and abs(run.x0 - previous.run.x0) <= 4 and not _LETTER.match(run.text))
        )
        if wraps:
            previous.extra.append(run)
        else:
            box.subs.append(_Caption(run))
    everyone = [head] + box.subs
    for value in values:
        beside = [c for c in everyone if c.run.line == value.line and c.run.x1 <= value.x0 + 1]
        above = [
            c for c in everyone
            if (c.extra or [c.run])[-1].line < value.line
            and min(c.run.x1, value.x1) - max(c.run.x0, value.x0) > 0
        ]
        if beside:
            owner = max(beside, key=lambda c: c.run.x1)
        elif above:
            owner = max(above, key=lambda c: ((c.extra or [c.run])[-1].line, -c.run.x0))
        else:
            owner = head
        owner.values.append(value)
    return box


# --- selections ------------------------------------------------------------------------------


@dataclass
class _Option:
    tick: BBox
    words: list[Word]
    state: str  # form_geometry SELECTED / NOT_SELECTED
    mark: Word | None

    @property
    def label(self) -> str:
        # "X is,  [ ] is not required.": the comma separates the options.
        return normalize_space(" ".join(w.text for w in self.words)).rstrip(",;")


def _options(lines: list[Line], rect: BBox, ticks: list[BBox]) -> tuple[list[_Option], list[Word]]:
    """The box's printed options, each its tick box's label and state (a
    mark inside the tick box is Selected, none is Not Selected); and any
    mark in the box that sits in none of its tick boxes — unclear, for
    review, never assigned to an option.

    A label is the words on the tick box's own line to its right, up to
    the next tick box, a wide gap, or the comma / full stop that ends it
    ("[X] award, [ ] notice to proceed."); a label that wraps goes on at
    the start of the next line when that line starts there. A label with
    no word in it ("671-339-8465" beside a drawn square) is no option."""

    inside = [t for t in ticks if _inside(t, rect)]
    words = [w for line in lines for w in line.words if _inside((w.x0, w.y0, w.x1, w.y1), rect)]
    marks = [w for w in words if w.text in _MARKS]
    options: list[_Option] = []
    claimed: set[int] = set()
    for tick in sorted(inside, key=lambda t: (t[1], t[0])):
        tx0, ty0, tx1, ty1 = tick
        mark = next((m for m in marks if tx0 - 1.5 <= (m.x0 + m.x1) / 2 <= tx1 + 1.5 and ty0 - 1.5 <= m.cy <= ty1 + 1.5), None)
        beside = [
            w for w in words
            if ty0 - 2 <= w.cy <= ty1 + 2 and 0 <= w.x0 - tx1 + 1 <= 14 and w is not mark and id(w) not in claimed
        ]
        if not beside:
            continue
        first = min(beside, key=lambda w: (abs(w.cy - (ty0 + ty1) / 2), w.x0))
        label = _label_from(first, words, inside, tick, claimed)
        # A wrapped label goes on where it started, on the next line, when
        # that line starts there (and above the next tick box).
        below = [t[1] for t in inside if t[1] > ty1 - 1]
        limit = min(below) if below else rect[3]
        if not label[-1].text.endswith((",", ".", ";")):
            nxt = [w for w in words if label[0].cy + 2 < w.cy < limit and id(w) not in claimed]
            if nxt:
                top = min(w.cy for w in nxt)
                line = sorted((w for w in nxt if abs(w.cy - top) <= 1.5), key=lambda w: w.x0)
                starts = [w for w in line if w.x0 >= tx1 - 1]
                if starts and abs(starts[0].x0 - label[0].x0) <= 3 and starts[0].size <= label[0].size * 1.05:
                    label += _label_from(starts[0], words, inside, tick, claimed | {id(w) for w in label})
        if not any(re.search(r"[A-Za-z]", w.text) for w in label):
            continue
        claimed |= {id(w) for w in label}
        options.append(_Option(tick, label, SELECTED if mark else NOT_SELECTED, mark))
    used = {id(o.mark) for o in options if o.mark}
    stray = [m for m in marks if id(m) not in used] if options else []
    return options, stray


def _label_from(first: Word, words: list[Word], ticks: list[BBox], tick: BBox, claimed: set[int]) -> list[Word]:
    """`first` and the words after it on its line, up to the next tick box,
    a wide gap, or a word that ends the option with "," "." or ";"."""

    row = sorted((w for w in words if abs(w.cy - first.cy) <= 1.5 and w.x0 >= first.x0 and id(w) not in claimed), key=lambda w: w.x0)
    label: list[Word] = []
    for w in row:
        if label and (w.x0 - label[-1].x1 > 10 or any(label[-1].x1 <= t[0] <= w.x0 for t in ticks if t != tick)):
            break
        label.append(w)
        if w.text.endswith((",", ";")) or (w.text.endswith(".") and not _ABBREVIATION.match(w.text)):
            break
    return label


# --- the page ---------------------------------------------------------------------------------


@dataclass
class VectorForm:
    fields: list[FieldCandidate]
    tables: list[TableCandidate]
    regions: list[StructuredRegion]
    frame: BBox | None = None


def read_vector_form(
    ids: _Ids,
    page_number: int,
    page,
    lines: list[Line],
    extraction_method: str,
    page_text: str,
    claimed: list[BBox] | None = None,
) -> VectorForm | None:
    """The drawn form on the page, box by box, or None when it has none."""

    rects = form_boxes(page)
    if not rects:
        return None
    claimed = claimed or []
    rects = [r for r in rects if not any(_inside(r, c) for c in claimed)]
    caption_size, sized = page_sizes(lines, rects)
    ticks = checkboxes(page)
    selections = {rect: _options(lines, rect, ticks) for rect in rects}
    taken = {rect: frozenset(id(w) for o in selections[rect][0] for w in o.words + ([o.mark] if o.mark else [])) for rect in rects}
    boxes = [(rect, _read(lines, rect, caption_size, sized, taken[rect])) for rect in rects]
    # Rules alone don't make a form (a ruled table under a title row splits
    # its rows differently too): a form numbers its boxes.
    if sum(1 for _, box in boxes if box is not None and box.item is not None) < _MIN_NUMBERED:
        return None
    result = VectorForm(fields=[], tables=[], regions=[], frame=_union(rects))
    page_words = [w for line in lines for w in line.words]
    table_rects = _form_tables(ids, page_number, boxes, extraction_method, page_text, result)
    with_options = {rect for rect, (options, _) in selections.items() if options}
    _form_fields(ids, page_number, [(r, b) for r, b in boxes if b is not None and r not in table_rects], extraction_method, result,
                 with_options)
    for rect, box in boxes:
        if rect in table_rects or box is None or box.head is None:
            continue
        options, stray = selections[rect]
        _choice_fields(ids, page_number, rect, box, options, stray, extraction_method, result, page_words)
    for rect, box in boxes:
        if box is not None:
            for seg in box.segments:
                seg.used = True
    return result if result.fields or result.tables else None


def _inside(rect: BBox, outer: BBox) -> bool:
    return rect[0] >= outer[0] - 1 and rect[1] >= outer[1] - 1 and rect[2] <= outer[2] + 1 and rect[3] <= outer[3] + 1


def _form_fields(ids: _Ids, page_number: int, boxes: list[tuple[BBox, _Box]], extraction_method: str, result: VectorForm,
                 with_options: set[BBox] = frozenset()) -> None:
    # A numbered box with no value of its own heads the lettered boxes
    # beside it in its row ("10. FOR INFORMATION CALL:" → A. NAME …).
    parents: dict[BBox, tuple[str, str]] = {}
    for rect, box in boxes:
        letter = box.letter
        if letter is None or box.item is not None:
            continue
        row = [(r, b) for r, b in boxes if abs(r[1] - rect[1]) <= _NEAR and r[0] < rect[0] and b.item is not None]
        if row:
            parent_rect, parent = max(row, key=lambda rb: rb[0][0])
            if not parent.head.values and not parent.subs:
                parents[rect] = (_code(parent.item), parent.item.group("name"))
    heading_parents = {p for p in parents.values()}
    for rect, box in boxes:
        if box.head is None:
            continue
        item = box.item
        code = _code(item) if item else None
        name = item.group("name") if item else box.head.text
        if rect in parents:
            parent_code, parent_name = parents[rect]
            letter = box.letter
            _emit(ids, page_number, rect, box.head, extraction_method, result,
                  code=parent_code, label=letter.group("name"), parent=parent_name, sub=letter.group("code"))
            for sub in box.subs:
                _emit(ids, page_number, rect, sub, extraction_method, result,
                      code=parent_code, label=sub.text, parent=parent_name, sub=letter.group("code"))
            continue
        if code and (code, name) in heading_parents:
            continue  # its lettered boxes carry its caption
        # A box holding only its options: they carry its caption.
        bare = rect in with_options and not box.head.values and not box.subs
        if (box.subs or box.head.values or code) and not bare:
            _emit(ids, page_number, rect, box.head, extraction_method, result, code=code, label=box.head.text)
        for sub in box.subs:
            letter = _LETTER.match(sub.text)
            _emit(ids, page_number, rect, sub, extraction_method, result, code=code,
                  label=letter.group("name") if letter else sub.text,
                  parent=name if code else None, sub=letter.group("code") if letter else None)


def _choice_fields(ids, page_number, rect, box: _Box, options: list[_Option], stray: list[Word], extraction_method, result,
                   page_words: list[Word]) -> None:
    """One field per printed option, under the box's item (and its lettered
    sub-item when the options sit on a lettered line: "13. … B. An offer
    guarantee [X] is, [ ] is not required")."""

    if not options:
        return
    item = box.item
    code = _code(item) if item else None
    parent = item.group("name") if item else box.head.text
    for option in options:
        own = _OWN_ITEM.match(option.label)
        if own:
            name = _TRAILING_PAREN.sub("", own.group("name")) or own.group("name")
            candidate = _field(
                ids, page_number, name, "X" if option.mark else "", "ruled_form_box",
                _union([(w.x0, w.y0, w.x1, w.y1) for w in option.words]), option.tick,
                f"{'[X]' if option.mark else '[ ]'} {option.label}", extraction_method,
            )
            candidate.box_code = _code(own)
            candidate.box_rect = rect
            candidate.box_choice = option.state if not stray else UNRECOGNIZED
            candidate.reasons, candidate.acceptance = [], "accepted"
            result.fields.append(candidate)
            continue
        sub = None
        line_words = [
            w for w in page_words
            if abs(w.cy - option.words[0].cy) <= 1.5 and w.x1 <= option.tick[0] + 1 and _inside((w.x0, w.y0, w.x1, w.y1), rect)
        ]
        if line_words:
            letter = _LETTER.match(" ".join(w.text for w in sorted(line_words, key=lambda w: w.x0)))
            sub = letter.group("code") if letter else None
        state = option.state if not stray else UNRECOGNIZED
        candidate = _field(
            ids, page_number, option.label, "X" if option.mark else "", "ruled_form_box",
            _union([(w.x0, w.y0, w.x1, w.y1) for w in option.words]), option.tick,
            f"{'[X]' if option.mark else '[ ]'} {option.label}", extraction_method,
        )
        candidate.box_code = code
        candidate.box_rect = rect
        candidate.box_caption = parent
        candidate.box_sub = sub
        candidate.box_choice = state
        candidate.reasons = []
        candidate.acceptance = "accepted"
        result.fields.append(candidate)


def _code(item: re.Match) -> str:
    return item.group("code").replace(" ", "")


def _emit(ids, page_number, rect, printed: _Caption, extraction_method, result, *, code, label,
          parent=None, sub=None) -> None:
    """One field: `printed` is the box's caption and its values; `parent`
    the caption of the item it is a sub-field of, `sub` its letter."""

    value = printed.value
    candidate = _field(
        ids, page_number, label, value, "ruled_form_box",
        printed.run.bbox, _union([r.bbox for r in printed.values]) if printed.values else None,
        f"{printed.text} {value}".strip(), extraction_method,
    )
    candidate.box_code = code
    candidate.box_rect = rect
    candidate.box_caption = parent
    candidate.box_sub = sub
    # Its place makes it a caption, and what is typed in the box its value
    # however long (an address block, a description); a printed box left
    # empty is a blank value.
    candidate.reasons = [
        r for r in candidate.reasons if not r.startswith("label_") and r not in ("value_is_prose", "value_too_long")
    ]
    if not value and candidate.reasons == ["empty_value"]:
        candidate.reasons = []
    candidate.acceptance = "rejected" if candidate.reasons else "accepted"
    result.fields.append(candidate)


# --- tables inside a form ----------------------------------------------------------------------


def _form_tables(ids, page_number, boxes, extraction_method, page_text, result: VectorForm) -> set[BBox]:
    """Rows of boxes ruled alike (≥ 3 rows, ≥ 3 columns, no numbered
    caption) are a table; returns the rects it takes."""

    bands: dict[tuple[float, float], list[tuple[BBox, _Box | None]]] = {}
    for rect, box in boxes:
        key = next((k for k in bands if abs(k[0] - rect[1]) <= _NEAR and abs(k[1] - rect[3]) <= _NEAR), (rect[1], rect[3]))
        bands.setdefault(key, []).append((rect, box))
    ordered = [sorted(band, key=lambda rb: rb[0][0]) for _, band in sorted(bands.items())]
    taken: set[BBox] = set()
    run: list[list[tuple[BBox, _Box | None]]] = []
    above: list[tuple[BBox, _Box | None]] | None = None  # the band before the run

    def numbered(band) -> bool:
        return any(b is not None and b.item is not None for _, b in band)

    def flush() -> None:
        if len(run) >= 3 and len(run[0]) >= 3 and sum(1 for band in run[1:] if len(band) >= 2) >= 2:
            # "11. TABLE OF CONTENTS" alone in the row above: the table's title.
            title = None
            if above and len(above) == 1 and above[0][1] is not None and above[0][1].head                     and not above[0][1].head.values and not above[0][1].subs:
                title = above[0][1].head.text
                taken.add(above[0][0])
            _build_table(ids, page_number, run, extraction_method, page_text, result, title)
            taken.update(r for band in run for r, _ in band)
        run.clear()

    def across(band) -> bool:
        if not run or len(band) != 1:
            return False
        left = min(r[0] for b in run for r, _ in b)
        right = max(r[2] for b in run for r, _ in b)
        rect = band[0][0]
        return rect[2] - rect[0] >= 0.9 * (right - left)

    for index, band in enumerate(ordered):
        if numbered(band) or across(band):
            flush()
            continue
        if run and not _aligned(run, band):
            flush()
        if not run:
            above = ordered[index - 1] if index else None
        run.append(band)
    flush()
    return taken


def _aligned(run, band) -> bool:
    """The band's box edges are a subset of the run's widest band's edges
    (a heading row spans several columns; its edges still fall on theirs)."""

    widest = max(run + [band], key=len)
    edges = sorted({round(r[0]) for r, _ in widest} | {round(r[2]) for r, _ in widest})
    return all(any(abs(e - x) <= 3 for x in edges) for r, _ in band for e in (round(r[0]), round(r[2])))


def _build_table(ids, page_number, run, extraction_method, page_text, result: VectorForm, title: str | None) -> None:
    widest = max(run, key=len)
    columns = [(r[0], r[2]) for r, _ in widest]

    def text_of(box: _Box | None) -> str:
        if box is None:
            return ""
        parts = [box.head.text] if box.head else []
        parts += [c.text for c in box.subs] + [c.value for c in [box.head] + box.subs if box.head and c.value]
        parts += [r.text for r in box.loose]
        return normalize_space(" ".join(p for p in parts if p))

    grid: list[list[str]] = []
    boxes_grid: list[list[BBox | None]] = []
    for band in run:
        cells = [""] * len(columns)
        rects: list[BBox | None] = [None] * len(columns)
        for rect, box in band:
            index = min(range(len(columns)), key=lambda i: abs(columns[i][0] - rect[0]))
            cells[index] = text_of(box)
            rects[index] = rect
        grid.append(cells)
        boxes_grid.append(rects)
    header, body, header_rects, body_rects = grid[0], grid[1:], boxes_grid[0], boxes_grid[1:]
    # Side-by-side halves under a repeated header ("(X) SEC. DESCRIPTION
    # PAGE(S)" twice): one table, the left half's rows then the right's.
    width = len(header)
    for half in range(1, width // 2 + 1):
        if width % half == 0 and width // half > 1 and all(
            header[i] == header[i % half] for i in range(width)
        ):
            pieces = width // half
            header, header_rects = header[:half], header_rects[:half]
            stacked, stacked_rects = [], []
            for piece in range(pieces):
                for row, rects in zip(body, body_rects):
                    cells = row[piece * half:(piece + 1) * half]
                    if any(cells):
                        stacked.append(cells)
                        stacked_rects.append(rects[piece * half:(piece + 1) * half])
            body, body_rects = stacked, stacked_rects
            break
    printed = all(header)
    table, regions = _table_from_grid(
        ids, page_number, "pdf_form_grid", extraction_method,
        header if printed else None, header_rects if printed else [],
        body if printed else [header] + body, body_rects if printed else [header_rects] + body_rects,
        page_text, _union([r for band in run for r, _ in band]),
    )
    table.caption = title
    result.tables.append(table)
    result.regions.extend(regions)
