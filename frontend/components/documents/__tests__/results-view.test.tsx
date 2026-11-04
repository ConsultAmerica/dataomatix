import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ResultsView, { columnOrder, deriveFields, derivePairs, isContentsPair } from "@/components/documents/results-view";
import { getDocumentPages, getSourceStructure } from "@/lib/documents";
import type { StagingCell, StagingDataset, StagingWorkbook } from "@/lib/staging-workbook";

vi.mock("@/lib/documents", () => ({
  getPageRender: vi.fn(() => new Promise(() => undefined)),
  getSourceStructure: vi.fn(() =>
    Promise.resolve({
      document_id: "d1",
      field_candidates: [
        { candidate_id: "c1", label_text: "Employee", raw_value: "Jane Doe", value_type_hint: "text",
          structural_relation: "same_line_separator", page: 1, label_bbox: [40, 78, 94, 91],
          value_bbox: [100, 78, 148, 91], acceptance: "accepted", quality_score: 0.9 },
        { candidate_id: "c2", label_text: "Noise", raw_value: "x", value_type_hint: null,
          structural_relation: "loose", page: 1, label_bbox: null, value_bbox: null, acceptance: "rejected", quality_score: 0.1 },
      ],
      table_candidates: [],
    }),
  ),
  getDocumentPages: vi.fn(() =>
    Promise.resolve([
      { document_id: "d1", page_number: 1, page_label: null, extraction_method: "native", final_text: "Gross Pay 2,000.00\nNet Pay 1,647.00",
        requires_ocr: false, ocr_attempted: false, ocr_succeeded: false, character_count: 30, word_count: 6, page_width: 612, page_height: 792 },
    ]),
  ),
}));

function cell(field: string, value: string | null, status: StagingCell["review_status"] = "Verified", page = 1): StagingCell {
  return {
    canonical_field: field,
    display_label: field,
    value,
    raw_value: value,
    value_type: "string",
    provenance: value === null ? null : {
      source_document_id: "d1", source_filename: "a.pdf", source_type: "pdf", source_page: page,
      source_bbox: [10, 20, 60, 30], evidence_text: value, extraction_method: "native", source_locator: null,
      source_region_id: null, anchor_text: null, highlight_text: null,
    },
    validation: { status: "passed", checks: [] },
    review_status: status,
    review_reasons: [],
  };
}

function dataset(partial: Partial<StagingDataset> & Pick<StagingDataset, "dataset_id" | "display_name" | "cardinality" | "columns" | "records">): StagingDataset {
  return { role: "business", description: null, identity_fields: [], ...partial } as StagingDataset;
}

const column = (key: string, label: string) => ({
  canonical_field: `x.${key}`, key, display_label: label, value_type: "string", expected: false,
});

function workbook(): StagingWorkbook {
  return {
    datasets: [
      dataset({
        dataset_id: "summary", display_name: "Document Summary", cardinality: "single",
        columns: [column("type", "Document Type"), column("pages", "Pages")],
        records: [{ record_id: "r", record_status: null, links_to_dataset: null,
                    cells: { "x.type": cell("x.type", "Pay Stub / Paycheck"), "x.pages": cell("x.pages", null) } }],
      }),
      dataset({
        dataset_id: "key_fields", display_name: "Key Fields", cardinality: "repeating",
        columns: [column("name", "Field"), column("value", "Value")],
        records: [
          { record_id: "k1", record_status: null, links_to_dataset: null,
            cells: { "x.name": cell("x.name", "Gross Pay"), "x.value": cell("x.value", "2,000.00") } },
          { record_id: "k2", record_status: null, links_to_dataset: null,
            cells: { "x.name": cell("x.name", "Employee"), "x.value": cell("x.value", "Jane Doe", "Needs Review") } },
        ],
      }),
      dataset({
        dataset_id: "lines", display_name: "Line Items", cardinality: "repeating",
        columns: [column("item", "Item"), column("amount", "Amount")],
        records: [{ record_id: "l1", record_status: null, links_to_dataset: null,
                    cells: { "x.item": cell("x.item", "Widget"), "x.amount": cell("x.amount", "10.00") } }],
      }),
      dataset({
        dataset_id: "qa", display_name: "QA", cardinality: "repeating", role: "qa",
        columns: [column("check", "Check")], records: [{ record_id: "q", record_status: null, links_to_dataset: null,
                                                         cells: { "x.check": cell("x.check", "ignored") } }],
      }),
    ],
  } as unknown as StagingWorkbook;
}

describe("Results view data", () => {
  it("lists single values and name/value rows as fields, other repeating data as tables", () => {
    const { fields, tables } = deriveFields(workbook());
    expect(fields.map((field) => [field.label, field.value])).toEqual([
      ["Document Type", "Pay Stub / Paycheck"],
      ["Gross Pay", "2,000.00"],
      ["Employee", "Jane Doe"],
    ]);
    expect(fields[1]).toMatchObject({ page: 1, bbox: [10, 20, 60, 30], status: "Verified" });
    expect(tables).toHaveLength(1);
    expect(tables[0]).toMatchObject({ title: "Line Items", headers: ["Item", "Amount"], rows: [["Widget", "10.00"]] });
  });

  it("merges layout pairs with key fields the layout pass missed, without duplicates or rejects", () => {
    const { fields } = deriveFields(workbook());
    const pairs = derivePairs(
      { document_id: "d1", field_candidates: [
        { candidate_id: "c1", label_text: "Employee", raw_value: "Jane Doe", value_type_hint: null, structural_relation: "",
          page: 1, label_bbox: null, value_bbox: [1, 2, 3, 4], acceptance: "accepted", quality_score: 0.8 },
        { candidate_id: "c2", label_text: "Noise", raw_value: "x", value_type_hint: null, structural_relation: "",
          page: 1, label_bbox: null, value_bbox: null, acceptance: "rejected", quality_score: 0.1 },
      ], table_candidates: [] },
      fields,
    );
    expect(pairs.map((pair) => [pair.label, pair.source])).toEqual([["Employee", "layout"], ["Gross Pay", "text"]]);
  });

  it("tells table-of-contents entries from data pairs", () => {
    expect(isContentsPair("B.1 Background", "11")).toBe(true);
    expect(isContentsPair("B.2.2.2 Exempt Labor Categories", "15")).toBe(true);
    expect(isContentsPair("Section C", "Description/Specifications/ ......................... 19")).toBe(true);
    expect(isContentsPair("C.1 Background/Purpose", "......................................... 19")).toBe(true);
    // Real values stay.
    expect(isContentsPair("Solicitation No", "GS06Q-17-RL-0004")).toBe(false);
    expect(isContentsPair("Issue Date", "October 7, 2016")).toBe(false);
    expect(isContentsPair("Quantity", "12")).toBe(false);
    expect(isContentsPair("B.3 Other Direct Cost Support", "Materials and travel")).toBe(false);
  });
});

describe("ResultsView", () => {
  it("shows summary cards, filters fields and outlines nothing until a value is chosen", async () => {
    render(<ResultsView documentId="d1" workbook={workbook()} typeLabel="Pay Stub / Paycheck" pageCount={1} />);
    expect(screen.getByText("Document type").nextSibling?.textContent).toBe("Pay Stub / Paycheck");
    expect(screen.getAllByTestId("results-field")).toHaveLength(3);
    fireEvent.change(screen.getByLabelText("Filter results"), { target: { value: "gross" } });
    expect(screen.getAllByTestId("results-field")).toHaveLength(1);
  });

  it("opens a document whose data is a table (FAR Data) on Tables, listed first", async () => {
    const far = {
      datasets: [dataset({
        dataset_id: "far_records", display_name: "FAR Data", cardinality: "repeating",
        columns: [column("number", "FAR Number"), column("title", "Title")],
        records: [{ record_id: "f1", record_status: null, links_to_dataset: null,
                    cells: { "x.number": cell("x.number", "7.107-1"), "x.title": cell("x.title", "General") } }],
      })],
    } as unknown as StagingWorkbook;
    render(<ResultsView documentId="d1" workbook={far} typeLabel="FAR Part" pageCount={1} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveTextContent("Tables");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("FAR Data")).toBeTruthy();
  });

  it("puts Clause Text and Provision Text straight after the identifier and title", () => {
    const headers = ["FAR Number", "Title", "Record Type", "Revision Date", "Provision Text", "Clause Text", "Section Text", "Source Reference"];
    expect(columnOrder(headers).map((index) => headers[index])).toEqual(
      ["FAR Number", "Title", "Clause Text", "Provision Text", "Section Text", "Record Type", "Revision Date", "Source Reference"]);
    expect(columnOrder(["Item", "Amount"])).toEqual([0, 1]);
  });

  it("hides columns blank on every row shown — per chosen type — and shows them on request", () => {
    const make = (id: string, type: string, text: string, form: string) => ({
      record_id: id, record_status: null, links_to_dataset: null,
      cells: { "x.number": cell("x.number", id), "x.title": cell("x.title", `Title ${id}`), "x.type": cell("x.type", type),
               "x.form": cell("x.form", form || null), "x.clause": cell("x.clause", text || null) },
    });
    const records = [
      ...Array.from({ length: 8 }, (_, i) => make(`52.2${i}`, "Clause", `(a) Text ${i}`, "")),
      ...Array.from({ length: 6 }, (_, i) => make(`52.3${i}`, "Reserved", "", "")),
    ];
    const far = { datasets: [dataset({ dataset_id: "far_records", display_name: "FAR Clauses & Provisions", cardinality: "repeating", records,
      columns: [column("number", "FAR Number"), column("title", "Title"), column("type", "Record Type"), column("form", "Form Number"), column("clause", "Clause Text")] })] } as unknown as StagingWorkbook;
    render(<ResultsView documentId="d1" workbook={far} typeLabel="FAR Regulation" pageCount={1} />);
    const table = screen.getByTestId("results-table");
    const headers = () => within(table).getAllByRole("columnheader").map((th) => th.textContent);
    // Form Number is blank everywhere: hidden; Clause Text leads after the title.
    expect(headers()).toEqual(["FAR Number", "Title", "Clause Text", "Record Type"]);
    expect(within(table).getByTestId("results-empty-columns")).toHaveTextContent("1 empty column hidden · Show");
    // Reserved rows have no text at all: only the identifier, title and type remain.
    fireEvent.click(within(table).getByRole("button", { name: /Reserved 6/ }));
    expect(headers()).toEqual(["FAR Number", "Title", "Record Type"]);
    fireEvent.click(within(table).getByTestId("results-empty-columns"));
    expect(headers()).toEqual(["FAR Number", "Title", "Clause Text", "Record Type", "Form Number"]);
    // Nothing about the rows changes: all 6 Reserved rows, every value as extracted.
    expect(within(table).getByText("6 of 14 rows")).toBeTruthy();
  });

  it("lays a large table out like the FAR grid: one line per row, type chips with counts, its own search", async () => {
    const records = Array.from({ length: 14 }, (_, index) => ({
      record_id: `f${index}`, record_status: null, links_to_dataset: null,
      cells: {
        "x.number": cell("x.number", `52.2${String(index).padStart(2, "0")}`),
        "x.title": cell("x.title", index === 3 ? "Gratuities" : `Clause ${index}`),
        "x.type": cell("x.type", index < 10 ? "Clause" : "Provision"),
        "x.amount": cell("x.amount", `${1000 + index}.00`),
      },
    }));
    const far = {
      datasets: [dataset({
        dataset_id: "far_records", display_name: "FAR Clauses & Provisions", cardinality: "repeating", records,
        columns: [column("number", "FAR Number"), column("title", "Title"), column("type", "Record Type"), column("amount", "Amount")],
      })],
    } as unknown as StagingWorkbook;
    render(<ResultsView documentId="d1" workbook={far} typeLabel="FAR Regulation" pageCount={1} />);
    const table = screen.getByTestId("results-table");
    expect(within(table).getByText("14 of 14 rows")).toBeTruthy();
    // Identifiers stay left; amounts go right.
    expect(within(table).getByText("52.203").className).not.toContain("text-right");
    expect(within(table).getByText("1003.00").className).toContain("text-right");
    fireEvent.click(within(table).getByRole("button", { name: /Provision 4/ }));
    expect(within(table).getByText("4 of 14 rows")).toBeTruthy();
    fireEvent.click(within(table).getByRole("button", { name: /All 14/ }));
    fireEvent.change(within(table).getByLabelText("Search FAR Clauses & Provisions"), { target: { value: "gratuities" } });
    expect(within(table).getByText("1 of 14 rows")).toBeTruthy();
  });

  it("names web-page tables by their clause and groups forms printed blank, headers kept", async () => {
    const cellOf = (text: string, column: number) => ({ row_index: 0, column_index: column, text, bbox: null });
    vi.mocked(getSourceStructure).mockResolvedValueOnce({
      document_id: "d1", field_candidates: [],
      table_candidates: [
        { candidate_id: "t1", page: null, bbox: null, acceptance: "accepted", structure_score: 0.9, headers: ["FAR Clause #", "Title"],
          source_locator: { section_path: ["Part 52", "52.204-27 Prohibition on a ByteDance Covered Application."] },
          rows: [[cellOf("52.204-27", 0), cellOf("Prohibition", 1)]] },
        { candidate_id: "t2", page: null, bbox: null, acceptance: "accepted", structure_score: 0.7, headers: ["Item No.", "Quantity"],
          source_locator: { section_path: ["Part 52", "52.211-8 Time of Delivery."] },
          rows: [[cellOf("", 0), cellOf("", 1)], [cellOf("", 0), cellOf("", 1)]] },
      ],
    } as never);
    vi.mocked(getDocumentPages).mockResolvedValueOnce([
      { document_id: "d1", page_number: 1, page_label: null, extraction_method: "html", final_text: "Part 52", requires_ocr: false,
        ocr_attempted: false, ocr_succeeded: false, character_count: 7, word_count: 2, page_width: 0, page_height: 0 },
    ] as never);
    const far = { datasets: [] } as unknown as StagingWorkbook;
    render(<ResultsView documentId="d1" workbook={far} typeLabel="FAR Regulation" pageCount={1} />);
    fireEvent.click(screen.getByRole("tab", { name: /Tables/ }));
    expect(await screen.findByText("52.204-27 Prohibition on a ByteDance Covered Application.")).toBeTruthy();
    const blank = screen.getByTestId("blank-tables");
    expect(blank).toHaveTextContent("1 fill-in table printed blank in the document — headers only");
    expect(blank).toHaveTextContent("52.211-8 Time of Delivery. · Item No. | Quantity · 2 blank rows");
    // A web page has no page image: the document pane starts closed and opens on request.
    await waitFor(() => expect(screen.getByTestId("toggle-document")).toHaveTextContent("Show document (no page image for this file)"));
    fireEvent.click(screen.getByTestId("toggle-document"));
    expect(screen.getByTestId("toggle-document")).toHaveTextContent("Hide document");
  });

  it("opens a document with fields on Fields", () => {
    render(<ResultsView documentId="d1" workbook={workbook()} typeLabel="Pay Stub" pageCount={1} />);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent?.replace(/\d+$/, ""))).toEqual(["Fields", "Key-value pairs", "Tables", "OCR text"]);
    expect(screen.getByRole("tab", { name: /Fields/ })).toHaveAttribute("aria-selected", "true");
  });

  it("shows OCR text per page with its method", async () => {
    render(<ResultsView documentId="d1" workbook={workbook()} typeLabel="Pay Stub" pageCount={1} />);
    fireEvent.click(screen.getByRole("tab", { name: /OCR text/ }));
    const page = await screen.findByText("Page 1");
    const article = page.closest("article")!;
    expect(within(article).getByText("Native text")).toBeTruthy();
    expect(article.textContent).toContain("Net Pay 1,647.00");
  });

  it("lists key-value pairs from the layout and the key fields", async () => {
    render(<ResultsView documentId="d1" workbook={workbook()} typeLabel="Pay Stub" pageCount={1} />);
    fireEvent.click(screen.getByRole("tab", { name: /Key-value pairs/ }));
    await waitFor(() =>
      expect(screen.getAllByTestId("results-pair").map((row) => row.textContent)).toEqual([
        expect.stringContaining("Jane Doe"),
        expect.stringContaining("2,000.00"),
      ]),
    );
  });
});
