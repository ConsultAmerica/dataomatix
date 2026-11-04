"""Golden source expectations for Increment 7.3.4 (extraction accuracy).

Every expected value below was read from the source document itself (its
printed page text or HTML DOM), never from the extractor's output. Each
expectation names the 7.3.4 implementation step expected to make it pass;
`fix=None` means it passes today and must keep passing.

Steps (7.3.4 order): 3 false tables / drawn-form boxes, 4 printed form
labels and sub-items, 5 repeating line-item records, 6 HTML spanned and
multi-level headers, 7 headerless tables (no invented headers), 8 printed
checkbox selections, 9 completeness and source references.

Not yet regression-verified (no real sample available, locally or in
production): SF1449 and SF30. See REQUIRED_COVERAGE below; their tests are
placeholders that skip until a real document is added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

REGRESSION = Path(__file__).resolve().parents[3] / "reference" / "regression"


@dataclass(frozen=True)
class Field:
    """A printed box: its item number, printed name and value. `parent` is
    the item's printed caption when the value is one of its sub-items
    (`sub` is the sub-item's printed letter: "A", "B")."""

    page: int | None
    item: str
    name: str
    value: str
    parent: str | None = None
    sub: str | None = None
    contains: bool = False  # value need only appear in the field's value
    fix: int | None = None


@dataclass(frozen=True)
class Choice:
    """A printed or fillable selection box and its expected state."""

    page: int
    item: str
    option: str
    state: str  # "Selected" | "Not Selected"
    fix: int | None = None


@dataclass(frozen=True)
class Table:
    """A genuine table: its printed headers (whitespace-normalised), and
    rows identified by their first cell with values each row must hold."""

    page: int | None
    headers: tuple[str, ...]
    rows: dict[str, tuple[str, ...]] = field(default_factory=dict)
    row_count: int | None = None
    title: str | None = None
    fix: int | None = None


@dataclass(frozen=True)
class NotATable:
    """Text that must not be read as a table (narrative columns, signature
    blocks, form boxes): no table on the page may contain it."""

    page: int | None
    text: str
    kind: str
    fix: int | None = None


@dataclass(frozen=True)
class NoLooseField:
    """A label that belongs to a record or a printed box and must not stand
    as a free field (repeated line-item attributes, PDF help text)."""

    pattern: str  # regex on the field's label or name
    reason: str
    fix: int | None = None


@dataclass(frozen=True)
class Doc:
    key: str
    file: str
    pages: int | None  # first N pages of the source (None: all)
    # What the document is (a document family), judged from the document
    # itself, never from the classifier's output.
    family: str | None = None
    fields: tuple[Field, ...] = ()
    choices: tuple[Choice, ...] = ()
    tables: tuple[Table, ...] = ()
    not_tables: tuple[NotATable, ...] = ()
    no_loose_fields: tuple[NoLooseField, ...] = ()


_CLIN = ("Item", "Supplies/Service", "Quantity", "Unit", "Unit Price", "Amount")
_SF336 = ("ITEM NO.", "SUPPLIES/SERVICES", "QUANTITY", "UNIT", "UNIT PRICE", "AMOUNT")
_THRESHOLDS = (
    "Trade agreement",
    "Supply contract (equal to or exceeding)",
    "Service contract (equal to or exceeding)",
    "Construction Ccontract (equal to or exceeding)",  # sic: printed so
)

DOCS: tuple[Doc, ...] = (
    Doc(
        key="SF1442",
        family="government_contract",
        file="SF1442 Award_N4019223D2803.pdf",
        pages=4,
        fields=(
            Field(1, "1", "SOLICITATION NO.", "N4019221R28000019"),
            Field(1, "3", "DATE ISSUED", "29-Sep-2023"),
            Field(1, "4", "CONTRACT NO.", "N4019223D2803"),
            Field(1, "5", "REQUISITION/PURCHASE REQUEST NO.", "ACQR5858342"),
            Field(1, "6", "PROJECT NO.", ""),
            Field(1, "7", "CODE", "N40192", parent="ISSUED BY"),
            Field(1, "8", "ADDRESS OFFER TO", "See Item 7", contains=True),
            Field(1, "9", "NAME", "DORIS CASTRO", parent="FOR INFORMATION CALL", sub="A"),
            Field(1, "9", "TELEPHONE NO.", "671-339-8465", parent="FOR INFORMATION CALL", sub="B", contains=True),
            Field(1, "12B", "CALENDAR DAYS", "10"),
            Field(2, "14", "NAME AND ADDRESS OF OFFEROR", "CHUGACH CONSOLIDATED SOLUTIONS, LLC", contains=True),
            Field(2, "15", "TELEPHONE NO.", "(907) 868-2875"),
            Field(2, "21", "ITEMS ACCEPTED", "SEE SCHEDULE"),
            Field(2, "22", "AMOUNT", "$600,000,000.00"),
            Field(2, "31A", "NAME OF CONTRACTING OFFICER", "DORIS CASTRO", contains=True),
            Field(2, "31C", "AWARD DATE", "29-Sep-2023"),
        ),
        choices=(
            Choice(1, "2", "NEGOTIATED (RFP)", "Selected"),
            Choice(1, "2", "SEALED BID (IFB)", "Not Selected"),
            Choice(1, "12A", "YES", "Selected"),
            Choice(1, "12A", "NO", "Not Selected"),
            # Printed "X is,  [ ] is not required." (corrected: the option
            # labels are the printed words beside each tick box).
            Choice(1, "13B", "is", "Selected"),
            Choice(1, "13B", "is not required", "Not Selected"),
        ),
        tables=(
            Table(4, ("ITEM NO", "SUPPLIES/SERVICES", "MAX QUANTITY", "UNIT", "UNIT PRICE", "MAX AMOUNT"),
                  rows={"0001": ("600,000,000", "Each", "$1.00", "$600,000,000.00")}, fix=5),
        ),
        not_tables=(
            NotATable(2, "30A. NAME AND TITLE OF CONTRACTOR", "signature block"),
            NotATable(1, "4. CONTRACT NO.", "numbered form boxes"),
        ),
        no_loose_fields=(
            # A value that is itself the next box's caption is a mis-pairing.
            NoLooseField(r"^value:\s*\d{1,2}[A-Z]?\.\s+[A-Z]", "a box caption read as another box's value"),
        ),
    ),
    Doc(
        key="SF33_FA30",
        family="government_contract",
        file="Contract - FA300224C0008 (2).pdf",
        pages=4,
        fields=(
            Field(1, "2", "CONTRACT NUMBER", "FA300224C0008"),
            Field(1, "3", "SOLICITATION NUMBER", "FA300223R00090009"),
            Field(1, "5", "DATE ISSUED", "21 Apr 2023"),
            Field(1, "6", "REQUISITION/PURCHASE NUMBER", "F2X3C34150A001"),
            Field(1, "10", "NAME", "Paul Lewis", parent="FOR INFORMATION CALL", sub="A"),
            Field(1, "10", "AREA CODE", "210", parent="FOR INFORMATION CALL", sub="B"),
            Field(1, "10", "NUMBER", "652-7824", parent="FOR INFORMATION CALL", sub="B"),
            Field(1, "10", "EXTENSION", "", parent="FOR INFORMATION CALL", sub="B"),
            Field(1, "10", "EMAIL ADDRESS", "paul.lewis.16@us.af.mil", parent="FOR INFORMATION CALL", sub="C"),
            Field(1, "20", "AMOUNT", "USD 24,131,140.28"),
        ),
        choices=(
            # SF33 prints the options in full (corrected from "NEGOTIATED (RFP)").
            Choice(1, "4", "NEGOTIATED (RFP) REQUEST FOR PROPOSAL", "Selected"),
            Choice(1, "4", "SEALED BID (IFB) INVITATION FOR BID", "Not Selected"),
        ),
        tables=(
            Table(3, _CLIN, rows={
                "0001": ("S216", "Firm Fixed Price", "10", "Months", "USD 142,035.17", "USD 1,420,351.70"),
                "0003": ("S216", "Cost No Fee", "1", "Lot", "USD 1,000,000.00"),
            }, row_count=5, fix=5),
            Table(4, _CLIN, row_count=5, fix=5),
            Table(1, ("(X)", "SECTION", "DESCRIPTION", "PAGE(S)")),
        ),
        no_loose_fields=(
            NoLooseField(r"^(label|name):\s*(\d+\s+)?(Enter |Click here|Sign here|Check if)",
                         "PDF help text used as a field name"),
            NoLooseField(r"^(label|name):\s*Product Service Code$", "line-item attribute outside its record", fix=5),
            NoLooseField(r"^(label|name):\s*Pricing Arrangement$", "line-item attribute outside its record", fix=5),
        ),
    ),
    Doc(
        key="SF33_47QRC",
        family="government_contract",
        file="Contract_47QRCA25DSF07 (2).pdf",
        pages=4,
        fields=(
            Field(2, "2", "CONTRACT NUMBER", "47QRCA25DSF07"),
            Field(2, "3", "SOLICITATION NUMBER", "47QRCA23R0001"),
            Field(2, "5", "DATE ISSUED", "02/03/2025"),
            Field(2, "6", "REQUISITION/PURCHASE NUMBER", "PR-24-0000408"),
            Field(2, "7", "CODE", "47QRCA", parent="ISSUED BY"),
            Field(2, "10", "NAME", "Gabrina Daniels", parent="FOR INFORMATION CALL", sub="A"),
            Field(2, "10", "AREA CODE", "240", parent="FOR INFORMATION CALL", sub="B"),
            Field(2, "10", "NUMBER", "541-1679", parent="FOR INFORMATION CALL", sub="B"),
            Field(2, "10", "E-MAIL ADDRESS", "gabrina.daniels@gsa.gov", parent="FOR INFORMATION CALL", sub="C"),
            Field(2, "20", "AMOUNT", "$2,500.00"),
            Field(2, "26", "NAME OF CONTRACTING OFFICER", "Esther Shannon"),
            Field(2, "28", "AWARD DATE", "04/15/2025"),
        ),
        choices=(
            # SF33 prints the options in full (corrected from "NEGOTIATED (RFP)").
            Choice(2, "4", "NEGOTIATED (RFP) REQUEST FOR PROPOSAL", "Selected"),
            Choice(2, "4", "SEALED BID (IFB) INVITATION FOR BID", "Not Selected"),
        ),
        tables=(
            Table(2, ("(X)", "SEC.", "DESCRIPTION", "PAGE(S)"), title="TABLE OF CONTENTS",
                  rows={"C": ("DESCRIPTION/SPECIFICATIONS/WORK STATEMENT", "16")},
                  row_count=17),  # sections A–M and the 4 printed PART rows
            Table(3, _SF336, rows={"00001": ("Funding Line", "2,500.00"), "10301": ("RD-541330-SB", "0.00", "$0.00")},
                  row_count=7, fix=5),
            Table(4, _SF336, row_count=8, fix=5),
        ),
        no_loose_fields=(
            NoLooseField(r"^(label|name):\s*Obligated Amount$", "line-item attribute outside its record"),
        ),
    ),
    Doc(
        key="FAR51_pdf",
        family="far_regulation",
        file="far_part_51.pdf",
        pages=None,
        not_tables=(NotATable(None, "51.101", "regulation text"),),
    ),
    Doc(
        key="FAR_final_rule",
        family="far_regulatory_change",
        file="far_final_rule_2026-04912.pdf",
        pages=None,
        tables=(
            Table(2, _THRESHOLDS, rows={
                "WTO GPA": ("$174,000", "$174,000", "$6,683,000"),
                "Australia FTA": ("105,767", "105,767", "6,683,000"),
                "Israeli Trade Act": ("50,000",),
            }),
            # A real one-row ruled table with short printed headers (FAR is a
            # word here, not a sign of prose).
            Table(1, ("Subject", "FAR case"), rows={"Trade Agreements Thresholds": ("2025–007",)}, row_count=1),
            Table(4, ("Subject", "FAR case"), rows={"Trade Agreements Thresholds": ("2025–007",)}, row_count=1),
            # Page 3 prints the last header correctly ("Construction contract").
            Table(3, _THRESHOLDS[:3] + ("Construction contract (equal to or exceeding)",),
                  rows={"Bahrain FTA": ("174,000", "174,000", "13,749,689")}),
        ),
        not_tables=(
            NotATable(1, "Federal Acquisition Regulation;", "multi-column narrative"),
            NotATable(4, "Commercial Products and Commercial", "multi-column narrative"),
        ),
    ),
    # A DOE contract (DE-EM0002639): its sections, clauses and CLINs.
    Doc(key="contract_sample3", file="sample3.pdf", pages=12, family="government_contract"),
    Doc(
        key="FAR52_html",
        family="far_regulation",
        file="part_52.html",
        pages=None,
        tables=(
            Table(None, ("Construction Material Description", "Unit of Measure", "Quantity", "Price (Dollars)*"),
                  title="Foreign and Domestic Construction Materials Price Comparison", row_count=6, fix=6),
            Table(None, (
                "Contract Type",
                "Incentive (Voluntary) — Instant Contract Rate",
                "Incentive (Voluntary) — Concurrent and Future Contract Rate",
                "Program Requirement (Mandatory) — Instant Contract Rate",
                "Program Requirement (Mandatory) — Concurrent and Future Contract Rate",
            ), rows={"Fixed-price (includes fixed-price-award-fee; excludes other fixed-price incentive contracts)": ("*50", "25")},
                row_count=3, fix=6),
            # A fill-in table: its printed headers, its blank cells kept.
            Table(None, ("NAICS Code", "Size standard")),
        ),
    ),
)

# What SF1449 and SF30 fixtures must cover once real samples are available.
REQUIRED_COVERAGE = {
    "SF1449": (
        "numbered blocks 1-31 with printed labels, sub-items (e.g. 17a/17b, 18a/18b)",
        "checkboxes (block 6, 11, 17b, 18b, 27a/27b, 29) as Selected / Not Selected / unclear",
        "line items 19-24 (ITEM NO. | SCHEDULE OF SUPPLIES/SERVICES | QUANTITY | UNIT | UNIT PRICE | AMOUNT) as records",
        "continuation pages of the schedule, blank signature blocks kept blank",
    ),
    "SF30": (
        "blocks 1-16 with printed numbering (2. AMENDMENT/MODIFICATION NO., 3. EFFECTIVE DATE …)",
        "block 9A/9B and 10A/10B pairs with their parent captions",
        "block 13 checkboxes (A-D) as a selection group",
        "block 14 description of amendment/modification kept as narrative, not a table",
    ),
}
