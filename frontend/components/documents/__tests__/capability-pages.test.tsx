import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CapabilityNav, { capabilityHref } from "@/components/documents/capability-nav";
import ParseView from "@/components/parse/parse-view";
import { blockMarkdown, type ParseBlock } from "@/lib/parse";
import * as stagingWorkbook from "@/lib/staging-workbook";
import { breadcrumbsForPath } from "@/lib/workspace-nav";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/documents/doc-1/parse",
}));
vi.mock("@/lib/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/documents")>()),
  getPageRender: vi.fn(() => Promise.reject(new Error("no render"))),
}));
vi.mock("@/lib/staging-workbook", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/staging-workbook")>()),
  downloadExport: vi.fn(() => Promise.resolve()),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({
    parse_version: 1,
    document: { id: "doc-1", filename: "Contract.pdf", content_type: "application/pdf", source_type: "pdf", checksum_sha256: "x", page_count: 1, processing_status: "completed" },
    run: { checksum_sha256: "x", structure: { status: "current", extractor_version: 1, current_extractor_version: 1 } },
    window: { start_page: 1, end_page: 1, page_limit: 1, next_start_page: null, total_pages: 1 },
    pages: [{
      page_number: 1, width: 612, height: 792, positioning: "spatial", extraction_method: "native", blocks: [], elements: [],
      completeness: { source_characters: 0, block_characters: 0, missing_characters: 0, missing_tokens: [], tables_with_cell_gaps: 0, complete: true, note: null },
    }],
    sections: { status: "none", style: "none", total: 0, rows: [] },
    masking: { applied: false, rule: null },
    warnings: [],
  })),
}));

const block = (over: Partial<ParseBlock>): ParseBlock => ({
  id: "p1.b0", index: 0, page: 1, type: "paragraph", source_kind: "paragraph", text: "", bbox: null, lines: [],
  table: null, locator: null, provenance: { extraction_method: "native", positioning: "spatial" }, ...over,
});

describe("Parse downloads", () => {
  beforeEach(() => vi.mocked(stagingWorkbook.downloadExport).mockClear());

  it.each([
    ["Excel", "xlsx"],
    ["CSV", "csv"],
  ])("downloads the whole parsed document as %s", async (label, format) => {
    render(<ParseView documentId="doc-1" />);
    fireEvent.click(await screen.findByRole("button", { name: `Download the parsed document as ${label}` }));
    await waitFor(() => expect(stagingWorkbook.downloadExport).toHaveBeenCalledWith(
      expect.objectContaining({ format, href: `/api/documents/doc-1/parse/export.${format}` }),
      `Contract - parsed.${format}`,
    ));
  });

  it("says why a download failed", async () => {
    vi.mocked(stagingWorkbook.downloadExport).mockRejectedValueOnce(new Error("Parse CSV download failed (403)"));
    render(<ParseView documentId="doc-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Download the parsed document as CSV" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Parse CSV download failed (403)");
  });
});

describe("document capability pages", () => {
  it("links each capability to its own page and marks the current one", () => {
    render(<CapabilityNav documentId="doc-1" active="parse" />);
    const nav = screen.getByRole("navigation", { name: "Document capabilities" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Parse", "Extract", "Classify", "Sections", "Split"]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/documents/doc-1/parse", "/documents/doc-1", "/documents/doc-1/classify", "/documents/doc-1/sections", "/documents/doc-1/split",
    ]);
    expect(within(nav).getByRole("link", { name: "Parse" })).toHaveAttribute("aria-current", "page");
    expect(capabilityHref("doc-1", "extract")).toBe("/documents/doc-1");
  });

  it("names the file and the capability in the breadcrumb", () => {
    expect(breadcrumbsForPath("/documents/doc-1/parse", { documentTitle: "Contract.pdf" }).map((crumb) => crumb.label)).toEqual([
      "Workspace", "Documents", "Contract.pdf", "Parse",
    ]);
    expect(breadcrumbsForPath("/documents/doc-1/sections", { documentTitle: "Contract.pdf" }).at(-2)).toEqual({
      label: "Contract.pdf", href: "/documents/doc-1",
    });
  });

  it("writes Markdown that keeps tables as tables and marks running text", () => {
    const table = block({
      type: "table", source_kind: "table",
      table: { headers: ["CLIN", "Amount"], rows: [["0001", "1,200.00"]], candidate_id: null, continues_from: null, continues_to: null, missing_in_cells: [] },
    });
    expect(blockMarkdown(table)).toBe("| CLIN | Amount |\n| --- | --- |\n| 0001 | 1,200.00 |");
    expect(blockMarkdown(block({ type: "heading", text: "Section B" }))).toBe("## Section B");
    expect(blockMarkdown(block({ type: "marginalia", text: "(End of clause)" }))).toBe("<!-- marginalia: (End of clause) -->");
    expect(blockMarkdown(block({ text: "(a) The Contractor shall…" }))).toBe("(a) The Contractor shall…");
  });
});
