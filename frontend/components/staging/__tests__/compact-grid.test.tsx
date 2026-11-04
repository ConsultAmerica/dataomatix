import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import StagingDatasetTable from "@/components/staging/staging-dataset-table";
import {
  getStagingRecord,
  type CellProvenance,
  type StagingCell,
  type StagingDataset,
  type StagingRecord,
} from "@/lib/staging-workbook";

vi.mock("@/lib/staging-workbook", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/staging-workbook")>()),
  getStagingRecord: vi.fn(),
}));

const getRecord = vi.mocked(getStagingRecord);

const HTML_PROVENANCE: CellProvenance = {
  source_document_id: "doc-far",
  source_filename: "part_52.html",
  source_type: "html",
  source_page: null,
  source_bbox: null,
  evidence_text: "Unique Entity Identifier (Oct 2016)",
  extraction_method: "far_dom",
  source_locator: {
    dom_path: "/html/body/article/article[3]/p[2]",
    element_id: "FAR_52_204_6",
    section_path: ["Part 52", "Subpart 52.2", "52.204-6 Unique Entity Identifier."],
    table_index: null,
    row_index: null,
    column_index: null,
    sheet_name: null,
    cell_ref: null,
  },
  source_region_id: null,
  anchor_text: "52.204-6 Unique Entity Identifier.",
  highlight_text: "Unique Entity Identifier (Oct 2016)",
};

function cell(field: string, label: string, value: string | null, withProvenance = false): StagingCell {
  return {
    canonical_field: field,
    display_label: label,
    value,
    raw_value: withProvenance ? value : null,
    value_type: "text",
    provenance: withProvenance && value != null ? HTML_PROVENANCE : null,
    validation: { status: "passed", checks: [] },
    review_status: value == null ? null : "Verified",
    review_reasons: [],
  };
}

const COLUMNS = [
  ["far.far_number", "FAR Number"],
  ["far.title", "Title"],
  ["far.official_heading", "Official Heading"],
  ["far.revision_date", "Revision"],
  ["far.clause_type", "Type"],
  ["far.section_text", "Actual Section Text"],
] as const;

function farDataset(): StagingDataset {
  const grid = ["far.far_number", "far.title", "far.official_heading", "far.revision_date", "far.clause_type"];
  const values: Record<string, string> = {
    "far.far_number": "52.204-6",
    "far.title": "Unique Entity Identifier",
    "far.official_heading": "Unique Entity Identifier (Oct 2016)",
    "far.revision_date": "Oct 2016",
    "far.clause_type": "Provision",
  };
  return {
    dataset_id: "far_clauses",
    display_name: "Clauses & Provisions",
    cardinality: "repeating",
    role: "business",
    description: null,
    columns: COLUMNS.map(([canonical_field, display_label]) => ({
      canonical_field,
      key: canonical_field,
      display_label,
      value_type: "text",
      expected: false,
    })),
    identity_fields: ["far.far_number", "far.title"],
    grid_fields: grid,
    compact: true,
    records: [
      {
        record_id: "far_clauses:FAR-52.204-6",
        cells: Object.fromEntries(grid.map((field) => [field, cell(field, field, values[field])])),
        record_status: "Verified",
        links_to_dataset: null,
      },
    ],
  };
}

function fullRecord(): StagingRecord {
  return {
    record_id: "far_clauses:FAR-52.204-6",
    record_status: "Verified",
    links_to_dataset: null,
    cells: {
      "far.far_number": cell("far.far_number", "FAR Number", "52.204-6", true),
      "far.title": cell("far.title", "Title", "Unique Entity Identifier", true),
      "far.official_heading": cell("far.official_heading", "Official Heading", "Unique Entity Identifier (Oct 2016)", true),
      "far.revision_date": cell("far.revision_date", "Revision", "Oct 2016", true),
      "far.clause_type": cell("far.clause_type", "Type", "Provision", true),
      "far.section_text": cell(
        "far.section_text",
        "Actual Section Text",
        "As prescribed in 4.607(b), insert the following provision:\n(a) Definition. As used in this provision-",
        true,
      ),
    },
  };
}

describe("compact grid (grid_fields)", () => {
  beforeEach(() => {
    getRecord.mockReset();
  });

  it("shows only the declared grid columns plus status — no long text in the grid", () => {
    render(<StagingDatasetTable dataset={farDataset()} documentId="doc-far" />);
    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent?.trim());
    // A leading select-all checkbox column, then the declared grid columns.
    expect(headers).toEqual(["", "FAR Number", "Title", "Official Heading", "Revision", "Type", "Status", "Details"]);
    expect(screen.queryByText("Actual Section Text")).toBeNull();
    expect(screen.queryByText("Evidence")).toBeNull();
  });

  it("opens a drawer that loads the full record with its text and source evidence", async () => {
    getRecord.mockResolvedValue(fullRecord());
    const onOpenSource = vi.fn();
    render(<StagingDatasetTable dataset={farDataset()} documentId="doc-far" onOpenSource={onOpenSource} />);
    fireEvent.click(screen.getByRole("button", { name: "Details" }));

    const drawer = await screen.findByRole("dialog", { name: "Record details" });
    expect(getRecord).toHaveBeenCalledWith("doc-far", "far_clauses", "far_clauses:FAR-52.204-6");
    await waitFor(() => expect(within(drawer).getByText(/insert the following provision/)).toBeTruthy());
    expect(within(drawer).getAllByText("#FAR_52_204_6").length).toBeGreaterThan(0);

    fireEvent.click(within(drawer).getAllByRole("button", { name: "View source evidence" })[0]);
    expect(onOpenSource).toHaveBeenCalledWith(
      expect.objectContaining({ sourceType: "html", evidenceText: "Unique Entity Identifier (Oct 2016)" }),
    );
  });

  it("shows every column of a dataset without grid fields; evidence lives in the record drawer", () => {
    const dataset = { ...farDataset(), grid_fields: [], compact: false };
    render(<StagingDatasetTable dataset={dataset} documentId="doc-far" />);
    // No record fills Actual Section Text: hidden until asked for, and said so.
    expect(screen.getAllByRole("columnheader").map((th) => th.textContent?.trim())).not.toContain("Actual Section Text");
    fireEvent.click(screen.getByTestId("empty-columns"));
    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent?.trim());
    expect(headers).toContain("Actual Section Text");
    // No technical columns in the business grid.
    expect(headers).not.toContain("Evidence");
    expect(headers).not.toContain("Location");
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByRole("dialog", { name: "Record details" })).toBeTruthy();
  });

  it("a full-text grid keeps rows one line high; complete values open in the drawer", () => {
    const body = "Unique Entity Identifier (Oct 2016)\n" + "(a) Definition. ".repeat(40) + "\n(End of provision)";
    const base = farDataset();
    const records = Array.from({ length: 30 }, (_, index) => ({
      ...base.records[0],
      record_id: `r${index}`,
      cells: { ...base.records[0].cells, "far.official_heading": cell("far.official_heading", "Official Heading", body) },
    }));
    render(<StagingDatasetTable documentId="doc-far" dataset={{ ...base, full_text: true, compact: false, records }} />);
    // The whole value is in the cell, on one ellipsized line.
    const oneLine = body.replace(/\s+/g, " ");
    const spans = screen.getAllByText(oneLine);
    expect(spans.length).toBe(30); // 100 rows per page by default
    expect(spans[0].className).toContain("truncate");
    expect(spans[0].closest("td")?.className).toContain("h-11");
    fireEvent.click(screen.getAllByRole("button", { name: "Details" })[0]);
    const drawer = screen.getByRole("dialog", { name: "Record details" });
    expect(within(drawer).getByText(/\(End of provision\)/)).toBeTruthy();
  }, 15_000); // a full-text grid: slow when the whole suite runs in parallel
});
