import { apiFetch, fetchWithRetry } from "@/lib/api";
import { downloadBlob } from "@/lib/export";

/** Mirrors backend services/clause_outline.py and GET /documents/{id}/clause-outline:
 * the rows Extracted Data shows and its Excel export writes — one dataset. */
export interface OutlineColumn {
  key: string;
  label: string;
}

export interface OutlineRecord {
  kind: "front" | "section" | "clause" | "paragraph" | "table_header" | "table_row";
  level: number;
  number: string;
  page_start: number;
  record_key: string | null;
  /** One value per column, in column order. */
  cells: string[];
}

export interface OutlineCheck {
  code: "not_in_body" | "sequence_gap" | "no_text";
  number: string;
  message: string;
}

export interface ClauseOutline {
  document_id: string;
  style: "far" | "numbered" | "none";
  columns: OutlineColumn[];
  records: OutlineRecord[];
  checks: OutlineCheck[];
  contents_pages: number[];
  coverage: { body_words: number; missing_words: number; missing_examples: string[] } | null;
}

export function getClauseOutline(documentId: string): Promise<ClauseOutline> {
  return apiFetch(`/api/documents/${documentId}/clause-outline`);
}

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function stem(name: string): string {
  return name.replace(/\.[A-Za-z0-9]{2,5}$/, "") || "document";
}

/** Extracted Data as Excel: the same columns, rows and values as the view. */
export async function downloadExtractedData(documentId: string, documentName: string): Promise<void> {
  const response = await fetchWithRetry(`/api/documents/${documentId}/extracted-data.xlsx`, undefined);
  if (!response.ok) throw new Error(`The Excel export failed (${response.status}).`);
  downloadBlob(await response.blob(), `${stem(documentName)} - extracted data.xlsx`, XLSX);
}

/** Several documents' Extracted Data in one workbook, a worksheet each. */
export async function downloadExtractedDataMany(documentIds: string[]): Promise<void> {
  const response = await fetchWithRetry("/api/documents/extracted-data/export.xlsx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_ids: documentIds }),
  });
  if (!response.ok) throw new Error(`The Excel export failed (${response.status}).`);
  downloadBlob(await response.blob(), `Extracted data - ${documentIds.length} documents.xlsx`, XLSX);
}
