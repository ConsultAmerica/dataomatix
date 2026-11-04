import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VerificationWorkspace, { recordAtPoint, reviewCounts, visibleTabs } from "@/components/verification/verification-workspace";
import { useSelectionStore, storeKey, setCells, type SelectionStore } from "@/lib/table-selection";
import type { StagingWorkbook } from "@/lib/staging-workbook";
import type { LayoutField, OriginalStructure } from "@/lib/original-structure";
import type { BusinessData, ValidationSummary } from "@/lib/verification";

vi.mock("@/components/viewers/document-viewer", () => ({
  default: ({ request }: { request: { pageNumber: number; region?: number[] | null } | null }) => (
    <div data-testid="viewer">{request ? `page ${request.pageNumber}${request.region ? " region" : ""}` : "none"}</div>
  ),
}));
vi.mock("@/components/smart-view/oracle-status", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/components/smart-view/oracle-status")>()),
  useOracleMappings: () => [],
}));
vi.mock("@/components/classification/classification-panel", () => ({ default: () => <div>classification panel</div> }));
vi.mock("@/components/review/document-audit-trail", () => ({ default: () => <div>audit trail</div> }));
vi.mock("@/components/validation/document-validation-panel", () => ({ default: () => <div>rules</div> }));
// The document check has its own tests (document-check-summary.test.tsx).
vi.mock("@/components/verification/document-check-summary", () => ({ default: () => null }));

const { reviewMock, exportMock, findMock } = vi.hoisted(() => ({
  reviewMock: vi.fn(() => Promise.resolve({ results: [{ record_key: "k", ok: true }], reviewed: 1 })),
  exportMock: vi.fn(() => Promise.resolve()),
  findMock: vi.fn(() => Promise.resolve({ query: "q", label: "Invoice Total", found: false, answers: [], message: "“Invoice Total” wasn't found in this document's printed or extracted values." })),
}));

function field(key: string, label: string, value: string, extra: Partial<LayoutField> = {}): LayoutField {
  return {
    kind: "field", id: key, record_key: key, group: "1. Contractor Information", label, document_value: value, blank: !value,
    extracted_value: value, effective_value: value, evidence: `${label} ${value}`, review_status: "Not reviewed", value_type: "text",
    found_by: "ruled form row", page: 1, bbox: [10, 10, 50, 20], value_bbox: [60, 10, 140, 20], flags: [], metadata: null, other_metadata: [],
    ...extra,
  };
}

const structure: OriginalStructure = {
  document_id: "d1", source_type: "pdf", pages: 2,
  sections: [{
    id: "s1", title: "A. General Information", page: 1, level: 1, parent: null,
    items: [field("field:1:a:legal-entity:0", "Legal Entity", "ORBITAL FIELD SERVICES, LLC"), field("field:1:a:cage:0", "Cage", "7QRT2")],
  }],
  unplaced: [],
  stats: { sections: 1, fields: 2, blank_fields: 0, tables: 0, table_rows: 0, needs_review: 0, unplaced: 0 },
};

const business: BusinessData = {
  document_class: "contract", document_class_label: "Contract", document_type: "Government Contract", subtype: null,
  skill: { skill_id: "contract_recognition", version: "1.0", name: "Contract Recognition" },
  sections: [{
    key: "contractor_information", label: "Contractor Information", canonical: true, values: [], tables: [],
    fields: [
      {
        key: "contractor_name", label: "Contractor Name", type: "text", required: true, date_role: null,
        value: "ORBITAL FIELD SERVICES, LLC", record_key: "field:1:a:legal-entity:0", page: 1, evidence: "Legal Entity …",
        source_label: "Legal Entity", confidence: 0.64, validation_status: "passed", review_status: "Not reviewed", issues: [],
        candidates: [{ record_key: "field:1:a:legal-entity:0", label: "Legal Entity", group: null, source_section: "A", value: "ORBITAL FIELD SERVICES, LLC",
          document_value: null, extracted_value: null, page: 1, evidence: null, found_by: null, confidence: 0.64, validation_status: null, review_status: "Not reviewed", layout_flags: [] }],
      },
      {
        key: "uei", label: "UEI", type: "identifier", required: false, date_role: null, value: null, record_key: null, page: null,
        evidence: null, source_label: null, confidence: null, validation_status: "not_found", review_status: null, issues: [], candidates: [],
      },
    ],
  }],
  other: { values: [], tables: [] },
  issues: [],
  stats: { fields: 2, found: 1, missing_required: 0, values: 0, tables: 0, other_values: 0 },
};

const validation: ValidationSummary = {
  groups: [
    { kind: "duplicate_candidates", label: "Duplicate extraction candidates", severity: "info", issues: [] },
    { kind: "conflicting_values", label: "Conflicting values", severity: "error", issues: [
      { kind: "conflicting_values", severity: "error", message: "Contract Number: Different values were found for this field", fields: ["contract_number"],
        values: { contract_number: "C1" }, candidates: ["C1", "C2"], record_keys: ["field:1:a:cage:0"], page: 1, section: "A" },
    ] },
  ],
  counts: { errors: 1, warnings: 0, info: 1 },
};

vi.mock("@/lib/original-structure", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/original-structure")>()),
  getOriginalStructure: vi.fn(() => Promise.resolve(structure)),
  reviewStructureRecords: reviewMock,
  getRecordHistory: vi.fn(() => Promise.resolve({ record_key: "k", entries: [] })),
}));
vi.mock("@/lib/verification", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/verification")>()),
  getBusinessData: vi.fn(() => Promise.resolve(business)),
  getValidationSummary: vi.fn(() => Promise.resolve(validation)),
  getDocumentDates: vi.fn(() => Promise.resolve({ status: "Unknown", reason: "No expiration date was identified in the document.", days_remaining: null, warning_days: 30, expiration: null, dates: [] })),
  downloadSelectedRecords: exportMock,
  findValue: findMock,
}));

function Harness({ initial = "business" }: { initial?: "business" | "validation" | "summary" }) {
  const [view, setView] = useState<string>(initial);
  return (
    <VerificationWorkspace documentId="d1" documentName="brief.pdf" pageCount={2} stagingProfileId="contract_v3"
      view={view as never} onViewChange={(next) => setView(next)} />
  );
}

beforeEach(() => {
  window.localStorage.clear();
  reviewMock.mockClear();
  exportMock.mockClear();
});

describe("tabs", () => {
  it("keeps Summary last and shows Tables / Oracle only where the document uses them", () => {
    expect(visibleTabs(structure, business)).toEqual(["business", "validation", "oracle"]);
    const withTables = { ...structure, stats: { ...structure.stats, tables: 1 } };
    expect(visibleTabs(withTables, { ...business, document_class: "identity" })).toEqual(["business", "tables", "validation"]);
    // A FAR Part's table lives in the Advanced Grid.
    expect(visibleTabs(structure, business, true)).toEqual(["business", "advanced", "validation", "oracle"]);
  });
});

describe("VerificationWorkspace", () => {
  it("has no Original File view: an old link or stored tab opens Smart Review", async () => {
    render(<VerificationWorkspace documentId="d1" documentName="brief.pdf" pageCount={2} stagingProfileId="contract_v3" view={"original" as never} onViewChange={() => {}} />);
    expect(await screen.findByRole("article", { name: "Contractor Name" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Smart Review" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("tab", { name: "Original File" })).toBeNull();
    expect(screen.queryByTestId("original-structure")).toBeNull();
  });

  it("selects and exports records in Smart Review, without approving anything", async () => {
    render(<Harness />);
    fireEvent.click(await screen.findByLabelText("Select Contractor Name"));
    expect(screen.getByTestId("selected-records")).toHaveTextContent("1 selected record");
    expect(reviewMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Export format"), { target: { value: "csv" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Export selected/ }));
    });
    expect(exportMock).toHaveBeenCalledWith("d1", ["field:1:a:legal-entity:0"], "csv", "brief.pdf");
  });

  it("opens a field's exact source region and reviews selected records with Approve & Next", async () => {
    render(<Harness />);
    const card = await screen.findByRole("article", { name: "Contractor Name" });
    fireEvent.click(within(card).getByRole("button", { name: "ORBITAL FIELD SERVICES, LLC" }));
    expect(screen.getByTestId("viewer")).toHaveTextContent("page 1 region");
    fireEvent.click(screen.getByLabelText("Select all records in Contractor Information"));
    fireEvent.click(screen.getByRole("button", { name: "Review selected" }));
    const bar = screen.getByTestId("review-selected-bar");
    expect(bar).toHaveTextContent("Reviewing 1 of 1");
    await act(async () => {
      fireEvent.click(within(bar).getByRole("button", { name: "Approve & Next" }));
    });
    expect(reviewMock).toHaveBeenCalledWith("d1", ["field:1:a:legal-entity:0"], "accept", {});
  });

  it("shows confidence, validation and review separately and corrects inline", async () => {
    render(<Harness initial="business" />);
    const card = await screen.findByRole("article", { name: "Contractor Name" });
    expect(within(card).getByText("64%")).toBeInTheDocument();
    expect(within(card).getByText("Valid")).toBeInTheDocument();
    expect(within(card).getByText("Not reviewed")).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: /Correct/ }));
    fireEvent.change(within(card).getByLabelText("Corrected Contractor Name"), { target: { value: "ORBITAL FIELD SVCS LLC" } });
    await act(async () => {
      fireEvent.click(within(card).getByRole("button", { name: "Save" }));
    });
    expect(reviewMock).toHaveBeenCalledWith("d1", ["field:1:a:legal-entity:0"], "correct", { value: "ORBITAL FIELD SVCS LLC" });
    // Optional fields the document doesn't print are listed once, not as cards.
    expect(screen.queryByRole("article", { name: "UEI" })).toBeNull();
    expect(screen.getByTestId("not-found-fields")).toHaveTextContent("1 field not found in this document");
    expect(screen.getByTestId("not-found-fields")).toHaveTextContent("UEI");
  });

  it("says when a requested value isn't in the document", async () => {
    render(<Harness initial="business" />);
    fireEvent.change(await screen.findByLabelText("Find a value"), { target: { value: "Extract Invoice Total" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Find" }));
    });
    expect(findMock).toHaveBeenCalledWith("d1", "Extract Invoice Total");
    expect(screen.getByTestId("find-result")).toHaveTextContent("wasn't found");
  });

  it("lists exceptions most serious first and shows the source of one", async () => {
    render(<Harness initial="validation" />);
    const groups = await screen.findAllByTestId("validation-group");
    expect(groups[0]).toHaveTextContent("Conflicting values");
    fireEvent.click(within(groups[0]).getByText(/Different values were found/));
    expect(screen.getByTestId("viewer")).toHaveTextContent("page 1");
  });

  it("keeps a view opened by link, which shows a tab only while it is open", async () => {
    render(<Harness initial="summary" />);
    const views = await screen.findByRole("tablist", { name: "Document workspace" });
    expect(within(views).getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(within(views).getByRole("tab", { name: "Validation" }));
    expect(within(views).queryByRole("tab", { name: "Summary" })).toBeNull();
    expect(screen.queryByRole("button", { name: /More views/ })).toBeNull();
  });

  it("puts the expiration status in Summary, the last tab", async () => {
    render(<Harness initial="summary" />);
    expect(await screen.findByTestId("expiration-status")).toHaveTextContent("Unknown");
    const tabs = within(screen.getByRole("tablist", { name: "Document workspace" })).getAllByRole("tab");
    expect(tabs[tabs.length - 1]).toHaveTextContent("Summary");
  });

  it("opens a record's details beside the list, with original, extracted and reviewed values", async () => {
    render(<Harness />);
    const card = await screen.findByRole("article", { name: "Contractor Name" });
    fireEvent.click(within(card).getByRole("button", { name: "ORBITAL FIELD SERVICES, LLC" }));
    const details = await screen.findByTestId("record-details");
    expect(details).toHaveTextContent("Original labelLegal Entity");
    expect(details).toHaveTextContent("Display labelContractor Name (Contractor Information)");
    expect(details).toHaveTextContent("Effective valueORBITAL FIELD SERVICES, LLC");
    expect(await within(details).findByTestId("record-history")).toHaveTextContent("No review decisions yet.");
    fireEvent.click(within(details).getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("record-details")).toBeNull();
  });

  it("counts missing, failed, conflicting and pending separately", async () => {
    render(<Harness />);
    await screen.findByRole("article", { name: "Contractor Name" });
    await waitFor(() => expect(screen.getByTestId("count-pending")).toHaveTextContent("2Pending review"));
    expect(screen.getByTestId("count-conflicts")).toHaveTextContent("1Conflicting candidates");
    expect(screen.getByTestId("count-pending")).toHaveTextContent("2Pending review");
    expect(reviewCounts(structure, business, validation)).toEqual({ missing: 0, failures: 0, conflicts: 1, pending: 2 });
  });

  it("switches density and filters fields as you type", async () => {
    render(<Harness initial="business" />);
    await screen.findByRole("article", { name: "Contractor Name" });
    fireEvent.click(screen.getByRole("radio", { name: /Compact/ }));
    expect(screen.getByRole("article", { name: "Contractor Name" })).toHaveAttribute("data-density", "compact");
    expect(window.localStorage.getItem("dx-verification-density")).toBe("compact");
    fireEvent.change(screen.getByLabelText("Search fields"), { target: { value: "orbital" } });
    await waitFor(() => expect(screen.queryByRole("article", { name: "UEI" })).toBeNull());
    expect(screen.getByRole("article", { name: "Contractor Name" })).toBeInTheDocument();
  });

  it("approves the selection only after confirming, record by record", async () => {
    reviewMock.mockResolvedValueOnce({ results: [{ record_key: "a", ok: false, error: "This value failed validation" }], reviewed: 0 } as never);
    render(<Harness />);
    fireEvent.click(await screen.findByLabelText("Select all records in Contractor Information"));
    fireEvent.click(screen.getByRole("button", { name: "Approve selected…" }));
    expect(reviewMock).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(within(screen.getByTestId("selection-toolbar")).getByRole("button", { name: "Approve" }));
    });
    expect(reviewMock).toHaveBeenCalledWith("d1", ["field:1:a:legal-entity:0"], "accept");
    expect(screen.getByRole("status")).toHaveTextContent("0 approved; 1 not approved (This value failed validation)");
  });
});

describe("source synchronization", () => {
  it("finds the field printed at a point only from recorded coordinates", () => {
    expect(recordAtPoint(structure, 1, 100, 15)).toBe("field:1:a:legal-entity:0");
    expect(recordAtPoint(structure, 1, 400, 400)).toBeNull();
    expect(recordAtPoint(structure, 2, 100, 15)).toBeNull();
  });
});

const workbook = {
  document_id: "d1",
  datasets: [{
    dataset_id: "key_fields", display_name: "Key Fields",
    records: [{ record_id: "r1", record_status: null, links_to_dataset: null, cells: {
      value: { canonical_field: "value", display_label: "Value", value: "ORBITAL FIELD SERVICES, LLC", raw_value: null, value_type: "text",
        provenance: { source_page: 1 } as never, validation: { status: "passed", checks: [] }, review_status: null, review_reasons: [] },
    } }],
  }],
} as unknown as StagingWorkbook;

let gridStore: SelectionStore | null = null;
function GridHarness() {
  const grid = useSelectionStore();
  useEffect(() => {
    gridStore = grid;
  });
  const [view, setView] = useState<string>("business");
  return (
    <VerificationWorkspace documentId="d1" documentName="brief.pdf" pageCount={2} stagingProfileId="contract_v3"
      view={view as never} onViewChange={(next) => setView(next)} workbook={workbook} gridSelection={grid} />
  );
}

describe("Advanced Grid selection", () => {
  it("selects the grid cell that is the same record, and back", async () => {
    render(<GridHarness />);
    fireEvent.click(await screen.findByLabelText("Select Contractor Name"));
    await waitFor(() => expect(gridStore!.get(storeKey("d1", "key_fields")).get("r1")?.has("value")).toBe(true));
    act(() => gridStore!.set(storeKey("d1", "key_fields"), (current) => setCells(current, ["r1"], ["value"], false),
      { documentId: "d1", datasetId: "key_fields", datasetName: "Key Fields" }));
    await waitFor(() => expect(screen.getByLabelText("Select Contractor Name")).not.toBeChecked());
  });
});
