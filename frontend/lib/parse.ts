import { apiFetch } from "@/lib/api";
import { downloadExport } from "@/lib/staging-workbook";

/** Mirrors backend source_structure/parse_view.py and GET /documents/{id}/parse
 * (docs/parse-api.md): a window of whole pages, each with its blocks in
 * reading order, its form fields, and how complete it is. */

export type BlockType = "heading" | "paragraph" | "table" | "header" | "footer" | "page_reference" | "marginalia";
export type BBox = [number, number, number, number];

export interface ParseLine {
  text: string;
  bbox: BBox | null;
  /** The line's words verbatim, when display cleanup (underline fill) changed its text. */
  raw_text?: string;
}

export interface ParseTable {
  headers: string[];
  rows: string[][];
  candidate_id: string | null;
  continues_from: string | null;
  continues_to: string | null;
  /** The table's own words, present only when its cells lost some. */
  source_lines?: string[] | null;
  missing_in_cells: string[];
}

export interface ParseBlock {
  id: string;
  index: number;
  page: number;
  type: BlockType;
  source_kind: "heading" | "paragraph" | "table";
  text: string;
  bbox: BBox | null;
  lines: ParseLine[];
  table: ParseTable | null;
  locator: string | null;
  provenance: { extraction_method: string; positioning: string };
}

export interface ParseElement {
  id: string;
  type: "form_field" | "checkbox";
  item_number: string | null;
  item_name: string | null;
  label: string;
  printed_value: string;
  extracted_value: string;
  reviewed_value: string;
  blank: boolean;
  choice: string | null;
  review_status: string | null;
  label_bbox: BBox | null;
  value_bbox: BBox | null;
  block_id: string | null;
}

export interface ParsePage {
  page_number: number;
  width: number | null;
  height: number | null;
  positioning: "spatial" | "text_only" | "none";
  extraction_method: string;
  blocks: ParseBlock[];
  /** null: unavailable (no stored structure); []: none on this page. */
  elements: ParseElement[] | null;
  completeness: {
    source_characters: number;
    block_characters: number;
    missing_characters: number;
    missing_tokens: string[];
    tables_with_cell_gaps: number;
    complete: boolean;
    note: string | null;
  };
}

export interface ParseSectionRow {
  kind: "section" | "clause" | "paragraph";
  level: number;
  number: string;
  heading: string;
  page_start: number;
}

export interface ParseResult {
  parse_version: number;
  document: {
    id: string;
    filename: string;
    content_type: string;
    source_type: "pdf" | "image" | "html";
    checksum_sha256: string;
    page_count: number;
    processing_status: string;
  };
  run: { checksum_sha256: string; structure: { status: string; extractor_version: number | null; current_extractor_version: number } };
  window: { start_page: number | null; end_page: number | null; page_limit: number; next_start_page: number | null; total_pages: number };
  pages: ParsePage[];
  sections: { status: "available" | "none"; style: string; total: number; rows: ParseSectionRow[] };
  masking: { applied: boolean; rule: string | null };
  warnings: string[];
}

export function getParse(documentId: string, startPage = 1, pageLimit = 1): Promise<ParseResult> {
  return apiFetch(`/api/documents/${documentId}/parse?start_page=${startPage}&page_limit=${pageLimit}`);
}

/** The whole parsed document as a file, laid out as the original reads. */
export function downloadParse(documentId: string, format: "xlsx" | "csv", documentName: string) {
  const stem = documentName.replace(/\.[A-Za-z0-9]{2,5}$/, "");
  return downloadExport(
    {
      capability_id: `parse_${format}`,
      label: `Parse ${format === "xlsx" ? "Excel" : "CSV"} download`,
      format,
      href: `/api/documents/${documentId}/parse/export.${format}`,
      dataset_id: null,
    },
    `${stem} - parsed.${format}`,
  );
}

export const BLOCK_LABELS: Record<BlockType, string> = {
  heading: "Heading",
  paragraph: "Text",
  table: "Table",
  header: "Header",
  footer: "Footer",
  page_reference: "Page number",
  marginalia: "Marginalia",
};

function markdownTable(table: ParseTable): string {
  const header = table.headers.length ? table.headers : (table.rows[0] ?? []).map((_, index) => `Column ${index + 1}`);
  const cell = (value: string) => value.replace(/\|/g, "\\|").replace(/\n/g, " ");
  const lines = [
    `| ${header.map(cell).join(" | ")} |`,
    `| ${header.map(() => "---").join(" | ")} |`,
    ...table.rows.map((row) => `| ${row.map(cell).join(" | ")} |`),
  ];
  return lines.join("\n");
}

/** One block as Markdown: readable, not the authoritative record (JSON is). */
export function blockMarkdown(block: ParseBlock): string {
  if (block.type === "table" && block.table) return markdownTable(block.table);
  if (block.type === "heading") return `## ${block.text}`;
  if (block.type === "header" || block.type === "footer" || block.type === "page_reference" || block.type === "marginalia") {
    return `<!-- ${block.type}: ${block.text} -->`;
  }
  return block.text;
}

export function pageMarkdown(page: ParsePage): string {
  return page.blocks.map(blockMarkdown).join("\n\n");
}
