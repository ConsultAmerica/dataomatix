"""Schema-neutral text-shape rules: is this a plausible field LABEL, is this
a plausible field VALUE, and what kind of value is it.

Labels are judged by grammatical shape using closed-class English words
(determiners, pronouns, auxiliaries/modals, subordinators) — never by a
business vocabulary. "Invoice Number", "Ship To" and "Payment Terms" pass
because they are short noun phrases, not because they are known fields;
"Contractor shall email" and "Please remit payment within" fail because
they contain finite-verb/imperative grammar.
"""

from __future__ import annotations

import re

from app.source_structure.models import ValueTypeHint

# Closed-class words. A label never STARTS with these (it would be a
# clause or prepositional phrase: "For additional information contact").
_NON_LABEL_START = frozenset(
    """a an the this that these those my your our their its his her
    we you they it he she i if when while whereas although because unless
    please kindly for in on at by with from into upon within about as
    and or but nor so yet not all any each every some no""".split()
)
# …and never CONTAINS these (finite verbs/modals/pronouns make a clause:
# "The supplier agrees that", "Payment is due").
_NON_LABEL_ANYWHERE = frozenset(
    """shall will must may might should would could can cannot
    is are was were be been being am has have had do does did
    agrees agree agreed means include includes including
    we you they he she i us them our your their this these those
    that which who whom whose where hereby herein thereof whereby""".split()
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'&./-]*|\d[\d,./-]*")
_SEPARATOR_TAIL = re.compile(r"\s*[:：]\s*$|\s*[-–—=]\s*$|\s*\.{2,}\s*$")

MAX_LABEL_WORDS = 6
MAX_LABEL_CHARS = 48
MAX_VALUE_CHARS = 240
MAX_VALUE_WORDS = 30


_ABBREVIATION = re.compile(r"\b([A-Z][A-Za-z]{0,3})\.(?=\s|$)")

_LEADING_BULLET = re.compile(r"^[•·▪◦‣⁃●*\-–]+\s*")


def strip_label_separator(label: str) -> str:
    return _LEADING_BULLET.sub("", _SEPARATOR_TAIL.sub("", label).strip()).strip()


def normalize_space(text: str) -> str:
    # Fonts that encode the printed hyphen as U+00AD (soft hyphen) would
    # otherwise yield "P-100" as an invisible-hyphen "P100" lookalike.
    return re.sub(r"\s+", " ", (text or "").replace("­", "-")).strip()


def label_rejection(label: str, value: str | None = None) -> str | None:
    """None when `label` has the shape of a concise field label; otherwise
    the structural reason it doesn't."""

    text = normalize_space(strip_label_separator(label))
    if not text:
        return "empty_label"
    if len(text) > MAX_LABEL_CHARS:
        return "label_too_long"
    words = _WORD_RE.findall(text)
    if not words:
        return "label_has_no_words"
    if len(words) > MAX_LABEL_WORDS:
        return "label_too_many_words"
    if not re.search(r"[A-Za-z]", text):
        return "label_has_no_letters"
    if "�" in text:
        return "label_has_unreadable_characters"
    lowered = [w.lower().strip(".'") for w in words]
    if lowered[0] in _NON_LABEL_START or (len(words) > 1 and lowered[0] in ("of", "to", "via")):
        return "label_starts_like_a_clause"
    if text[0].islower() and len(words) >= 3:
        return "label_is_lowercase_fragment"
    if any(w in _NON_LABEL_ANYWHERE for w in lowered):
        return "label_contains_verb_or_pronoun"
    # A short capitalized token's period is an abbreviation ("Invoice No.",
    # "Ref. No.", "Acct."), not the end of a sentence.
    unabbreviated = _ABBREVIATION.sub(r"\1", text)
    if re.search(r"[.!?;]\s+\S", unabbreviated) or unabbreviated.endswith(
        (".", "!", "?", ";", ",")
    ):
        return "label_has_sentence_punctuation"
    digits = sum(ch.isdigit() for ch in text)
    if digits > len(text) * 0.4:
        return "label_mostly_digits"
    # Sentence-case prose starts capitalized and continues lowercase; a
    # 5-6 word all-lowercase-tail phrase is more likely a sentence fragment
    # than a field label unless it is short.
    if len(words) >= 5 and all(w[0].islower() for w in words[1:] if w[0].isalpha()):
        return "label_reads_as_sentence_fragment"
    return None


# Option words printed beside SF tick boxes ("is", "is not required.") are
# not field labels on their own; they complete the parent caption.
_FRAGMENT_OPTION_START = frozenset("""is are was were am be being been not""".split())
_PROPER_CHOICE_OPTION = re.compile(
    r"^(yes|no|y|n|true|false|n/?a|none|other|sealed\s+bid|negotiated)(\s*\([^)]*\))?$",
    re.I,
)


def is_fragment_option_label(label: str) -> bool:
    """True when a tick-box option is a clause fragment, not a field name."""

    text = normalize_space(strip_label_separator(label)).rstrip(".,;:")
    if not text:
        return True
    if _PROPER_CHOICE_OPTION.match(text):
        return False
    # All-caps solicitation options ("NEGOTIATED (RFP)") stay as printed.
    if text.isupper() and len(text) <= 40:
        return False
    words = _WORD_RE.findall(text)
    if not words:
        return True
    if words[0].lower().strip(".'") in _FRAGMENT_OPTION_START:
        return True
    return label_rejection(text) is not None


def format_choice_field_name(option_label: str, parent_caption: str | None = None) -> str:
    """Readable name for a printed tick option under its form caption.

    SF 1442 item 13B prints ``B. An offer guarantee [X] is, [ ] is not
    required.`` — the option words alone are not usable Field Names; fold
    them into the parent caption when they are fragments.
    """

    option = normalize_space(strip_label_separator(option_label)).rstrip(".,;:")
    parent = normalize_space(strip_label_separator(parent_caption or "")).rstrip(".,;:")
    # Drop a lettered lead from the parent if it was included ("B. …").
    parent = re.sub(r"^[A-Z][.)]\s+", "", parent).strip()
    if not option:
        return parent or "Option"
    if not is_fragment_option_label(option):
        return option
    if not parent:
        return option
    if option.lower() in parent.lower():
        return parent[0].upper() + parent[1:] if parent and parent[0].islower() else parent
    if parent.lower().endswith(option.lower()):
        return parent[0].upper() + parent[1:] if parent[0].islower() else parent
    combined = f"{parent} {option}"
    return combined[0].upper() + combined[1:] if combined[0].islower() else combined


_LIST_MARKER = re.compile(r"^\(?([a-z]|\d{1,2}|[ivx]{1,4})[.)]$", re.I)


def value_rejection(value: str) -> str | None:
    text = normalize_space(value)
    if not text:
        return "empty_value"
    if len(text) > MAX_VALUE_CHARS:
        return "value_too_long"
    words = text.split()
    if len(words) > MAX_VALUE_WORDS:
        return "value_is_prose"
    if not re.search(r"[A-Za-z0-9]", text):
        return "value_has_no_content"
    lowered = {w.lower().strip(".,;:'\"()") for w in words}
    # A clause (finite verb / modal / pronoun) is narrative, not a value:
    # "This section does not preclude…", "A price proposal is not required".
    if len(words) >= 6 and lowered & _NON_LABEL_ANYWHERE:
        return "value_is_prose"
    # Names, titles, addresses and codes are mostly capitalized or numeric;
    # a long run of lowercase words is running text.
    alpha = [w for w in words if w[:1].isalpha()]
    if len(words) >= 8 and alpha and sum(1 for w in alpha if w[0].islower()) / len(alpha) >= 0.6:
        return "value_is_prose"
    lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
    if lines and sum(1 for line in lines if _LIST_MARKER.match(line)) >= max(1, len(lines) // 2):
        return "value_is_list_markers"
    return None


_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
_PHONE_RE = re.compile(r"^(\+?\d{1,3}[\s.-]?)?(\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(\s*(x|ext\.?)\s*\d+)?$", re.I)
_CURRENCY_RE = re.compile(
    r"^(\(?-?\s*(?:[$€£¥]|USD|EUR|GBP|CAD|AUD)\s*-?[\d,]+(?:\.\d+)?\)?|-?[\d,]+\.\d{2}\s*(?:USD|EUR|GBP|CAD|AUD)?|\(?-?[\d]{1,3}(?:,\d{3})+(?:\.\d{2})?\)?)$",
    re.I,
)
_PERCENT_RE = re.compile(r"^-?\d+(?:\.\d+)?\s*%$")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
_DATE_RES = (
    re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(rf"^\d{{1,2}}[\s-](?:{_MONTHS})\.?[\s-]\d{{2,4}}$", re.I),
    re.compile(rf"^(?:{_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}$", re.I),
)
_TIME_RE = re.compile(r"\d{1,2}:\d{2}(:\d{2})?\s*(am|pm)?", re.I)
_BOOLEAN_RE = re.compile(r"^(yes|no|true|false|y|n|checked|unchecked|x|☒|☐|✓)$", re.I)
_ADDRESS_RE = re.compile(
    r"\d+\s+\w+.*\b[A-Z]{2}\s+\d{5}(-\d{4})?\b|\bP\.?\s?O\.?\s+Box\s+\d+",
    re.I | re.S,
)
_IDENTIFIER_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9][A-Za-z0-9#/._-]{2,40}$")


def infer_value_type(value: str) -> ValueTypeHint:
    text = normalize_space(value)
    if not text:
        return "text"
    if _EMAIL_RE.match(text):
        return "email"
    if _PHONE_RE.match(text):
        return "phone"
    if _PERCENT_RE.match(text):
        return "percentage"
    if _CURRENCY_RE.match(text):
        return "currency"
    for date_re in _DATE_RES:
        if date_re.match(text):
            return "date"
    date_part = _TIME_RE.sub("", text).strip(" ,T")
    if date_part != text and any(date_re.match(date_part) for date_re in _DATE_RES):
        return "datetime"
    if _NUMBER_RE.match(text.replace(",", "")):
        return "number"
    if _BOOLEAN_RE.match(text):
        return "boolean"
    if _ADDRESS_RE.search(value or "") and len(text.split()) >= 3:
        return "address"
    if _IDENTIFIER_RE.match(text):
        return "identifier"
    return "text"


def is_numeric_value(text: str) -> bool:
    return infer_value_type(text) in ("currency", "number", "percentage")


_LOWERCASE_JOINERS = frozenset("of to and for per in on at by the or a an de".split())


def candidate_quality(label_text: str, value: str, relation: str) -> tuple[float, list[str]]:
    """Non-blocking quality signals for an ACCEPTED label/value candidate.

    Acceptance says "structurally this is a label/value pair"; these flags
    say how much a consuming profile should trust it (e.g. a bold
    "INFORMATION" next to "AREA CODE" is structurally a pair but reads as
    two form captions). Shape only — no vocabulary. Score = 1 − 0.2/flag.
    """

    flags: list[str] = []
    words = label_text.split()
    letters = [ch for ch in label_text if ch.isalpha()]
    if len(words) == 1:
        flags.append("single_word_label")
    if len(letters) >= 2 and all(ch.isupper() for ch in letters) and len(words) >= 2:
        flags.append("all_caps_label")
    if any(w[0].islower() and w.lower() not in _LOWERCASE_JOINERS for w in words[1:] if w[:1].isalpha()):
        flags.append("label_has_lowercase_words")

    value_text = normalize_space(value)
    value_words = value_text.split()
    value_letters = [ch for ch in value_text if ch.isalpha()]
    if (
        2 <= len(value_words) <= 4
        and value_letters
        and all(ch.isupper() for ch in value_letters)
        and not any(ch.isdigit() for ch in value_text)
    ):
        flags.append("value_looks_like_label")
    lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
    if len(lines) >= 3 and all(len(line.split()) <= 2 for line in lines):
        flags.append("value_is_list")
    if value_text.endswith((",", ";", "-", "–")):
        flags.append("value_truncated")
    if relation == "left_right_typography":
        flags.append("pairing_by_typography_only")
    if relation == "left_right_whitespace":
        flags.append("pairing_by_position_only")

    return round(max(0.0, 1.0 - 0.2 * len(flags)), 2), flags
