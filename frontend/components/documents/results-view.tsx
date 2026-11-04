"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Copy,
  FileText,
  KeyRound,
  ListChecks,
  Loader2,
  ScanText,
  Search,
  Table2,
} from "lucide-react";

import {
  getDocumentPages,
  getPageRender,
  getSourceStructure,
  type SourceBox,
  type SourceStructure,
  type SourceTableCandidate,
} from "@/lib/documents";
import type { StagingCell, StagingDataset, StagingWorkbook } from "@/lib/staging-workbook";
import type { DocumentPage, PageRender } from "@/types/document";

/**
 * Results: everything read from the document in one place — the page on
 * the left with the selected value outlined, and on the right the staged
 * Fields, every Key-value pair found, Tables and the OCR text. Nothing is
 * recomputed here; each tab shows what the backend stored.
 */

type ResultsTab = "fields" | "pairs" | "tables" | "ocr";
type Status = "Verified" | "Needs Review" | "Missing" | null;

interface Located {
  page: number | null;
  bbox: SourceBox | null;
}

interface FieldRow extends Located {
  id: string;
  group: string;
  /** From a label/value dataset (Key Fields, Licence Data…): also a pair. */
  pairLike: boolean;
  /** Platform details (file name, status), not read from the document. */
  system: boolean;
  label: string;
  value: string;
  status: Status;
  note: string | null;
}

interface PairRow extends Located {
  id: string;
  label: string;
  value: string;
  source: "layout" | "text";
  quality: number | null;
}

interface TableView extends Located {
  id: string;
  title: string;
  headers: string[];
  rows: string[][];
  /** Every body cell is empty as printed: a form left to fill in. */
  blank?: boolean;
}

// A repeating dataset whose records are "field name → value" rows (Key
// Fields, Passport Data, Licence Data) lists as fields, not as a table.
const NAME_KEYS = new Set(["name", "field"]);
const VALUE_KEYS = ["value", "printed"];

function text(value: StagingCell["value"] | undefined): string {
  if (value === null || value === undefined) return "";
  return typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
}

function located(cell: StagingCell | undefined): Located {
  const provenance = cell?.provenance;
  return { page: provenance?.source_page ?? null, bbox: provenance?.source_bbox ?? null };
}

function nameValueColumns(dataset: StagingDataset): [string, string] | null {
  const keys = dataset.columns.map((column) => column.key);
  const name = keys.find((key) => NAME_KEYS.has(key));
  const value = VALUE_KEYS.find((key) => keys.includes(key));
  return name && value ? [name, value] : null;
}

function cellByKey(dataset: StagingDataset, cells: Record<string, StagingCell>, key: string) {
  const column = dataset.columns.find((item) => item.key === key);
  return column ? cells[column.canonical_field] : undefined;
}

export function deriveFields(workbook: StagingWorkbook): { fields: FieldRow[]; tables: TableView[] } {
  const fields: FieldRow[] = [];
  const tables: TableView[] = [];
  for (const dataset of workbook.datasets) {
    if (dataset.role !== "business" || dataset.records.length === 0) continue;
    const pair = nameValueColumns(dataset);
    if (dataset.cardinality === "single") {
      for (const record of dataset.records) {
        for (const column of dataset.columns) {
          const cell = record.cells[column.canonical_field];
          const value = text(cell?.value);
          if (!value) continue;
          fields.push({
            id: `${dataset.dataset_id}:${record.record_id}:${column.key}`,
            group: dataset.display_name,
            pairLike: false,
            system: cell?.provenance?.source_type === "system",
            label: column.display_label,
            value,
            status: cell?.review_status ?? null,
            note: null,
            ...located(cell),
          });
        }
      }
    } else if (pair) {
      const [nameKey, valueKey] = pair;
      const extra = dataset.columns.find((column) => column.key === "consistency");
      for (const record of dataset.records) {
        const valueCell = cellByKey(dataset, record.cells, valueKey);
        const value = text(valueCell?.value);
        const label = text(cellByKey(dataset, record.cells, nameKey)?.value);
        if (!label || !value) continue;
        fields.push({
          id: `${dataset.dataset_id}:${record.record_id}`,
          group: dataset.display_name,
          pairLike: true,
          system: valueCell?.provenance?.source_type === "system",
          label,
          value,
          status: valueCell?.review_status ?? record.record_status ?? null,
          note: extra ? text(record.cells[extra.canonical_field]?.value) || null : null,
          ...located(valueCell),
        });
      }
    } else {
      const columns = dataset.grid_fields?.length
        ? dataset.columns.filter((column) => dataset.grid_fields!.includes(column.canonical_field))
        : dataset.columns;
      const first = dataset.records[0]?.cells[columns[0]?.canonical_field];
      tables.push({
        id: dataset.dataset_id,
        title: dataset.display_name,
        headers: columns.map((column) => column.display_label),
        rows: dataset.records.map((record) => columns.map((column) => text(record.cells[column.canonical_field]?.value))),
        ...located(first),
      });
    }
  }
  return { fields, tables };
}

/** A page reference as a contents page prints it: "11", or a title with
 * leader dots ending in a page number. */
const PAGE_REFERENCE = /^\s*(?:[\s\S]*?[.·…_]{3,}\s*)?\d{1,4}\s*$/;
const NUMBERED_HEADING = /^\s*(?:[A-Z]{1,2}\.\d+(?:\.\d+)*|Section\s+[A-Z]\b|PART\s+[IVX]+\b|ARTICLE\s+\d+|Subpart\s+\d|\d+(?:\.\d+)+)/i;

/** A table-of-contents entry read as a label/value pair ("B.1 Background" → "11"). */
export function isContentsPair(label: string, value: string): boolean {
  return PAGE_REFERENCE.test(value) && (NUMBERED_HEADING.test(label) || /[.·…]{6,}/.test(value));
}

export function derivePairs(structure: SourceStructure | null, fields: FieldRow[]): PairRow[] {
  const pairs: PairRow[] = (structure?.field_candidates ?? [])
    .filter((candidate) => candidate.acceptance !== "rejected" && candidate.raw_value.trim())
    .map((candidate) => ({
      id: candidate.candidate_id,
      label: candidate.label_text,
      value: candidate.raw_value.trim(),
      source: "layout" as const,
      quality: candidate.quality_score,
      page: candidate.page,
      bbox: candidate.value_bbox ?? candidate.label_bbox,
    }));
  const seen = new Set(pairs.map((pair) => pair.label.toLowerCase()));
  for (const field of fields) {
    if (!field.pairLike || seen.has(field.label.toLowerCase())) continue;
    seen.add(field.label.toLowerCase());
    pairs.push({ id: `field:${field.id}`, label: field.label, value: field.value, source: "text", quality: null,
                 page: field.page, bbox: field.bbox });
  }
  return pairs;
}

function detectedTables(structure: SourceStructure | null): TableView[] {
  return (structure?.table_candidates ?? [])
    .filter((table: SourceTableCandidate) => table.acceptance === "accepted" && table.rows.length > 0)
    .map((table, index) => {
      const width = Math.max(table.headers.length, ...table.rows.map((row) => row.length));
      const rows = table.rows.map((row) => {
        const cells = Array<string>(width).fill("");
        for (const cell of row) if (cell.column_index < width) cells[cell.column_index] = cell.text;
        return cells;
      });
      // Named after the clause it sits in (a web page's headings), else by number.
      const section = table.caption || table.source_locator?.section_path?.at(-1);
      return {
        id: table.candidate_id,
        title: `${section ? section : `Table ${index + 1}`}${table.page ? ` · page ${table.page}` : ""}`,
        headers: Array.from({ length: width }, (_, column) => table.headers[column] ?? ""),
        rows,
        blank: rows.every((row) => row.every((cell) => !cell.trim())),
        page: table.page,
        bbox: table.bbox,
      };
    });
}

const STATUS_STYLE: Record<string, string> = {
  Verified: "bg-success/10 text-success",
  "Needs Review": "bg-warning/10 text-warning",
  Missing: "bg-surface-soft text-text-muted",
};

function StatusPill({ status }: { status: Status }) {
  if (!status) return null;
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[status]}`}>
      {status === "Verified" ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : null}
      {status === "Needs Review" ? <AlertTriangle className="h-3 w-3" aria-hidden="true" /> : null}
      {status}
    </span>
  );
}

function StatCard({ label, value, icon: Icon, tone }: { label: string; value: string; icon: typeof FileText; tone: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${tone}`}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-[11px] leading-tight text-text-muted">{label}</p>
        <p className="truncate text-sm font-semibold text-foreground" title={value}>{value}</p>
      </div>
    </div>
  );
}

function highlightMatches(content: string, query: string) {
  if (!query) return content;
  const lower = content.toLowerCase();
  const needle = query.toLowerCase();
  const parts: ReactNode[] = [];
  let index = 0;
  let at = lower.indexOf(needle);
  while (at !== -1) {
    parts.push(content.slice(index, at));
    parts.push(<mark key={at} className="rounded bg-warning/30 px-0.5 text-foreground">{content.slice(at, at + needle.length)}</mark>);
    index = at + needle.length;
    at = lower.indexOf(needle, index);
  }
  parts.push(content.slice(index));
  return parts;
}

function PageViewer({ documentId, page, pageCount, onPage, box }: {
  documentId: string;
  page: number;
  pageCount: number;
  onPage: (page: number) => void;
  box: SourceBox | null;
}) {
  const [renders, setRenders] = useState<Record<number, PageRender>>({});
  const [failed, setFailed] = useState<Record<number, boolean>>({});
  const render = renders[page];

  useEffect(() => {
    if (renders[page] || failed[page]) return;
    let active = true;
    getPageRender(documentId, page)
      .then((result) => active && setRenders((current) => ({ ...current, [page]: result })))
      .catch(() => active && setFailed((current) => ({ ...current, [page]: true })));
    return () => {
      active = false;
    };
  }, [documentId, page, renders, failed]);

  const overlay = render && box && render.page_width > 0 && render.page_height > 0
    ? {
        left: `${(box[0] / render.page_width) * 100}%`,
        top: `${(box[1] / render.page_height) * 100}%`,
        width: `${((box[2] - box[0]) / render.page_width) * 100}%`,
        height: `${((box[3] - box[1]) / render.page_height) * 100}%`,
      }
    : null;

  return (
    <div className="flex h-full flex-col rounded-2xl border border-border bg-surface-soft/60">
      <div className="flex items-center justify-between border-b border-border px-3 py-2 text-xs text-text-secondary">
        <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
          <FileText className="h-3.5 w-3.5" aria-hidden="true" /> Document
        </span>
        <span className="inline-flex items-center gap-1">
          <button type="button" className="rounded-md p-1 hover:bg-surface disabled:opacity-40" disabled={page <= 1}
                  onClick={() => onPage(page - 1)} aria-label="Previous page">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="tabular-nums">Page {page} of {pageCount}</span>
          <button type="button" className="rounded-md p-1 hover:bg-surface disabled:opacity-40" disabled={page >= pageCount}
                  onClick={() => onPage(page + 1)} aria-label="Next page">
            <ChevronRight className="h-4 w-4" />
          </button>
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {render ? (
          <div className="relative mx-auto w-full max-w-[640px] overflow-hidden rounded-lg bg-white shadow-md">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={render.image_data_url} alt={`Page ${page}`} className="block w-full" />
            {overlay && (
              <span
                className="pointer-events-none absolute rounded-sm border-2 border-primary bg-primary/15 shadow-[0_0_0_4px_rgba(37,99,235,0.15)] transition-all duration-300"
                style={overlay}
                data-testid="results-highlight"
              />
            )}
          </div>
        ) : failed[page] ? (
          <p className="p-6 text-center text-sm text-text-muted">This page could not be rendered.</p>
        ) : (
          <div className="flex h-64 items-center justify-center text-text-muted">
            <Loader2 className="h-5 w-5 animate-spin" aria-label="Loading page" />
          </div>
        )}
      </div>
    </div>
  );
}

/** A cell value that is an amount or a count (right-aligned): digits with
 * grouping or decimals, a currency or a percent. Identifiers such as
 * "52.000" or "INV-0001" in a number/code column are not amounts. */
const AMOUNT = /^[\s$€£(-]*\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?$|^[\s$€£(-]*\d+(?:\.\d{2})?\)?%?$/;
const IDENTIFIER_HEADER = /\b(number|no\.?|#|code|id|clause|section|item|ref(erence)?)\b/i;
/** A column with a few repeated values ("Record Type", "Status") filters the table. */
const FACET_HEADER = /\b(record type|type|status|category|kind)\b/i;
const FROZEN = 1;

function amountColumns(table: TableView): boolean[] {
  return table.headers.map((header, column) => {
    if (IDENTIFIER_HEADER.test(header)) return false;
    const values = table.rows.map((row) => row[column]).filter((cell) => cell?.trim());
    return values.length > 0 && values.filter((cell) => AMOUNT.test(cell)).length / values.length >= 0.8;
  });
}

function facetColumn(table: TableView): number {
  return table.headers.findIndex((header, column) => {
    if (!FACET_HEADER.test(header)) return false;
    const distinct = new Set(table.rows.map((row) => row[column]).filter(Boolean));
    return distinct.size > 1 && distinct.size <= 12;
  });
}

/** One table, laid out like the FAR records grid: one line per row with the
 * full text on hover, a sticky header and first column, its own search and,
 * where it has a type column, filter chips with counts. */
/** A regulation's body text columns ("Provision Text", "Clause Text",
 * "Section Text") read first: straight after the identifier and title. */
const TEXT_COLUMN = /\b(clause|provision|section)\s+text\b/i;
const TITLE_COLUMN = /\b(title|heading|name)\b/i;

export function columnOrder(headers: string[]): number[] {
  const all = headers.map((_, index) => index);
  const text = all.filter((index) => TEXT_COLUMN.test(headers[index]));
  if (text.length === 0) return all;
  const lead = TITLE_COLUMN.test(headers[1] ?? "") ? 2 : 1;
  const rest = all.filter((index) => !text.includes(index));
  // Provision and clause text before section text, as the request orders them.
  const ranked = [...text].sort((a, b) => rank(headers[a]) - rank(headers[b]));
  return [...rest.slice(0, lead), ...ranked, ...rest.slice(lead)];
}

function rank(header: string): number {
  return /clause/i.test(header) ? 0 : /provision/i.test(header) ? 1 : 2;
}

function DataTable({ table, filter }: { table: TableView; filter: string }) {
  const [query, setQuery] = useState("");
  const [facet, setFacet] = useState<string | null>(null);
  const amounts = useMemo(() => amountColumns(table), [table]);
  const facetAt = useMemo(() => facetColumn(table), [table]);
  const counts = useMemo(() => {
    if (facetAt < 0) return [];
    const byValue = new Map<string, number>();
    for (const row of table.rows) if (row[facetAt]) byValue.set(row[facetAt], (byValue.get(row[facetAt]) ?? 0) + 1);
    return [...byValue.entries()].sort((a, b) => b[1] - a[1]);
  }, [table, facetAt]);
  const needles = [filter, query.trim().toLowerCase()].filter(Boolean);
  const rows = table.rows.filter((row) =>
    (facet === null || row[facetAt] === facet) && needles.every((needle) => row.some((cell) => cell.toLowerCase().includes(needle))));
  const large = table.rows.length > 12;
  const order = useMemo(() => columnOrder(table.headers), [table.headers]);
  // Columns blank on every row shown (all of them, or the chosen type's)
  // are hidden — counted beside the row count, one click to show.
  const [showEmpty, setShowEmpty] = useState(false);
  const emptyColumns = order.filter((column, position) => position >= FROZEN && rows.length > 0 && rows.every((row) => !row[column]?.trim()));
  const shown = showEmpty ? order : order.filter((column) => !emptyColumns.includes(column));

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface" data-testid="results-table">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-3 py-2">
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground" title={table.title}>{table.title}</p>
        {emptyColumns.length > 0 && (
          <button type="button" onClick={() => setShowEmpty((value) => !value)} aria-pressed={showEmpty}
                  className="shrink-0 text-xs text-text-secondary underline-offset-2 hover:text-foreground hover:underline" data-testid="results-empty-columns">
            {showEmpty ? `Hide ${emptyColumns.length} empty column${emptyColumns.length === 1 ? "" : "s"}`
              : `${emptyColumns.length} empty column${emptyColumns.length === 1 ? "" : "s"} hidden · Show`}
          </button>
        )}
        <p className="shrink-0 text-xs tabular-nums text-text-muted">{rows.length} of {table.rows.length} rows</p>
      </div>
      {(large || counts.length > 0) && (
        <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-3 py-2">
          {large && (
            <label className="flex h-7 min-w-[12rem] flex-1 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 text-xs text-text-muted sm:max-w-xs">
              <Search className="h-3.5 w-3.5" aria-hidden="true" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${table.title}…`}
                     aria-label={`Search ${table.title}`} className="min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-text-muted" />
            </label>
          )}
          {counts.length > 0 && (
            <div className="flex flex-wrap gap-1" role="group" aria-label={`Filter by ${table.headers[facetAt]}`}>
              {[["All", table.rows.length] as const, ...counts].map(([value, count]) => {
                const selected = value === "All" ? facet === null : facet === value;
                return (
                  <button key={value} type="button" aria-pressed={selected} onClick={() => setFacet(value === "All" ? null : value)}
                          className={`h-7 rounded-full border px-2.5 text-xs ${selected ? "border-primary bg-primary text-white" : "border-border bg-surface text-text-secondary hover:border-primary hover:text-foreground"}`}>
                    {value} <span className="tabular-nums opacity-80">{count}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
      <div className="max-h-[560px] overflow-auto">
        <table className="w-full min-w-max border-separate border-spacing-0 text-left text-[13px]">
          <thead>
            <tr>
              {shown.map((column, position) => (
                <th key={column} scope="col"
                    className={`sticky top-0 h-8 max-w-[18rem] truncate border-b border-border bg-surface-soft px-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary ${position < FROZEN ? "left-0 z-30" : "z-20"} ${amounts[column] ? "text-right" : ""}`}>
                  {table.headers[column] || `Column ${column + 1}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="group">
                {shown.map((column, position) => {
                  const cell = row[column] ?? "";
                  return (
                    <td key={column} title={cell && cell.length > 40 ? cell : undefined}
                        className={`h-8 max-w-[18rem] truncate border-b border-border/70 px-2 align-middle group-hover:bg-surface-soft ${position < FROZEN ? "sticky left-0 z-10 bg-surface font-medium" : ""} ${amounts[column] ? "text-right tabular-nums" : ""} ${cell ? "text-foreground" : "text-text-muted"}`}>
                      {cell || "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={Math.max(1, shown.length)} className="px-3 py-6 text-center text-sm text-text-muted">No rows match.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ResultsView({ documentId, workbook, typeLabel, pageCount }: {
  documentId: string;
  workbook: StagingWorkbook;
  typeLabel: string;
  pageCount: number;
}) {
  const { fields, tables: stagedTables } = useMemo(() => deriveFields(workbook), [workbook]);
  // A document whose data is a table (a FAR Part's "FAR Data") opens on
  // Tables, listed first; one with fields (an invoice) opens on Fields.
  const tablesFirst = fields.length === 0 && stagedTables.length > 0;
  const [tab, setTab] = useState<ResultsTab>(tablesFirst ? "tables" : "fields");
  const [filter, setFilter] = useState("");
  const [structure, setStructure] = useState<SourceStructure | null>(null);
  const [pages, setPages] = useState<DocumentPage[] | null>(null);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<{ id: string; bbox: SourceBox | null } | null>(null);
  const [copied, setCopied] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    getSourceStructure(documentId).then((result) => active && setStructure(result)).catch(() => undefined);
    getDocumentPages(documentId).then((result) => active && setPages(result)).catch(() => active && setPages([]));
    return () => {
      active = false;
    };
  }, [documentId]);

  const allPairs = useMemo(() => derivePairs(structure, fields), [structure, fields]);
  // Contents entries (a heading and its page number) aren't data: set aside,
  // counted and one click away, never dropped.
  const contentsPairs = useMemo(() => {
    const direct = allPairs.filter((pair) => isContentsPair(pair.label, pair.value));
    // A page that is mostly contents entries: its other "heading → page number" pairs are too.
    const perPage = new Map<number, number>();
    for (const pair of direct) if (pair.page) perPage.set(pair.page, (perPage.get(pair.page) ?? 0) + 1);
    const contentsPages = new Set([...perPage].filter(([, count]) => count >= 5).map(([page]) => page));
    return allPairs.filter((pair) => direct.includes(pair) || (pair.page != null && contentsPages.has(pair.page) && PAGE_REFERENCE.test(pair.value)));
  }, [allPairs]);
  const [showContents, setShowContents] = useState(false);
  const pairs = showContents ? allPairs : allPairs.filter((pair) => !contentsPairs.includes(pair));
  const tables = useMemo(() => [...stagedTables, ...detectedTables(structure)], [stagedTables, structure]);
  const blankTables = tables.filter((table) => table.blank);
  // A web page or text file has no page image to show: its pane starts closed.
  const textOnly = pages !== null && pages.length > 0 && pages.every((item) => !item.page_width);
  const [documentOpen, setDocumentOpen] = useState<boolean | null>(null);
  const showDocument = documentOpen ?? !textOnly;
  const needle = filter.trim().toLowerCase();
  const matches = (...values: string[]) => !needle || values.some((value) => value.toLowerCase().includes(needle));
  const needsReview = fields.filter((field) => field.status === "Needs Review").length;
  const ocrPages = (pages ?? []).filter((item) => item.extraction_method?.toLowerCase().includes("ocr")).length;
  const totalPages = Math.max(1, pageCount, pages?.length ?? 0);

  function select(item: { id: string } & Located) {
    setSelected({ id: item.id, bbox: item.bbox });
    if (item.page) setPage(item.page);
  }

  const tablesTab = { id: "tables" as const, label: "Tables", count: tables.length, icon: Table2 };
  const tabs: { id: ResultsTab; label: string; count: number; icon: typeof FileText }[] = [
    ...(tablesFirst ? [tablesTab] : []),
    { id: "fields", label: "Fields", count: fields.length, icon: ListChecks },
    { id: "pairs", label: "Key-value pairs", count: pairs.length, icon: KeyRound },
    ...(tablesFirst ? [] : [tablesTab]),
    { id: "ocr", label: "OCR text", count: pages?.length ?? 0, icon: ScanText },
  ];

  const groups = useMemo(() => {
    const byGroup = new Map<string, FieldRow[]>();
    for (const field of fields) {
      if (!matches(field.label, field.value, field.group)) continue;
      byGroup.set(field.group, [...(byGroup.get(field.group) ?? []), field]);
    }
    // The document's own values first; platform details last.
    return [...byGroup.entries()].sort(
      ([, a], [, b]) => Number(a.every((row) => row.system)) - Number(b.every((row) => row.system)),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields, needle]);

  return (
    <section className="space-y-3" data-testid="results-view">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <StatCard label="Document type" value={typeLabel} icon={FileText} tone="bg-primary-soft text-primary" />
        <StatCard label="Fields extracted" value={fields.length.toLocaleString()} icon={ListChecks} tone="bg-success/10 text-success" />
        <StatCard label="Needs review" value={needsReview.toLocaleString()} icon={AlertTriangle}
                  tone={needsReview ? "bg-warning/10 text-warning" : "bg-surface-soft text-text-muted"} />
        <StatCard label="Pages" value={`${totalPages}${ocrPages ? ` · ${ocrPages} OCR` : ""}`} icon={ScanText}
                  tone="bg-surface-soft text-text-secondary" />
      </div>

      <div className="flex justify-end">
        <button type="button" onClick={() => setDocumentOpen(!showDocument)} aria-expanded={showDocument} aria-controls="results-document"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-soft hover:text-foreground"
          data-testid="toggle-document">
          {showDocument ? <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />}
          {showDocument ? "Hide document" : textOnly ? "Show document (no page image for this file)" : "Show document"}
        </button>
      </div>

      {/* The document is the narrower pane, so the data side shows more columns. */}
      <div className={`grid gap-4 ${showDocument ? "lg:grid-cols-[minmax(0,2fr)_minmax(0,5fr)]" : ""}`}>
        {showDocument && (
          <div id="results-document" className="h-[50vh] lg:sticky lg:top-4 lg:h-[calc(100vh-7rem)]">
            <PageViewer documentId={documentId} page={page} pageCount={totalPages} onPage={(next) => { setPage(next); setSelected(null); }}
                        box={selected?.bbox ?? null} />
          </div>
        )}

        <div className="min-w-0 rounded-2xl border border-border bg-surface shadow-sm">
          <div className="flex gap-1 overflow-x-auto border-b border-border px-2" role="tablist" aria-label="Results">
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
                className={[
                  "-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-3 text-sm transition-colors",
                  tab === item.id ? "border-primary font-medium text-primary" : "border-transparent text-text-secondary hover:text-foreground",
                ].join(" ")}
              >
                <item.icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
                <span className="rounded-full bg-surface-soft px-1.5 text-[11px] tabular-nums text-text-muted">{item.count}</span>
              </button>
            ))}
          </div>

          <div className="border-b border-border px-4 py-2.5">
            <label className="flex items-center gap-2 text-sm text-text-muted">
              <Search className="h-4 w-4" aria-hidden="true" />
              <input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder={tab === "ocr" ? "Search the text…" : "Filter by label or value…"}
                className="w-full bg-transparent py-1 text-foreground outline-none placeholder:text-text-muted"
                aria-label="Filter results"
              />
            </label>
          </div>

          <div className="max-h-[calc(100vh-14rem)] overflow-auto p-4">
            {tab === "fields" && (
              groups.length === 0 ? (
                <p className="py-10 text-center text-sm text-text-muted">{fields.length ? "No fields match the filter." : "No fields were extracted from this document yet."}</p>
              ) : (
                <div className="space-y-5">
                  {groups.map(([group, rows]) => (
                    <div key={group}>
                      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">{group}</p>
                      <ul className="divide-y divide-border/70 overflow-hidden rounded-xl border border-border">
                        {rows.map((field) => (
                          <li key={field.id}>
                            <button
                              type="button"
                              onClick={() => select(field)}
                              className={[
                                "grid w-full grid-cols-[minmax(0,2fr)_minmax(0,3fr)_9.5rem] items-center gap-3 px-3 py-2.5 text-left transition-colors",
                                selected?.id === field.id ? "bg-primary-soft/60" : "hover:bg-surface-soft/70",
                              ].join(" ")}
                              data-testid="results-field"
                            >
                              <span className="truncate text-sm text-text-secondary" title={field.label}>{field.label}</span>
                              <span className="min-w-0">
                                <span className="block break-words text-sm font-medium text-foreground">{field.value}</span>
                                {field.note && <span className="text-[11px] text-text-muted">{field.note}</span>}
                              </span>
                              <span className="flex items-center justify-end gap-2">
                                {field.page ? <span className="text-[11px] tabular-nums text-text-muted">p.{field.page}</span> : null}
                                <StatusPill status={field.status} />
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )
            )}

            {tab === "pairs" && contentsPairs.length > 0 && (
              <p className="mb-2 flex flex-wrap items-center gap-x-2 text-xs text-text-secondary" data-testid="contents-pairs">
                {showContents
                  ? `Showing ${contentsPairs.length} table-of-contents entr${contentsPairs.length === 1 ? "y" : "ies"} (heading and page number).`
                  : `${contentsPairs.length} table-of-contents entr${contentsPairs.length === 1 ? "y" : "ies"} (heading and page number) not listed.`}
                <button type="button" onClick={() => setShowContents((value) => !value)} aria-expanded={showContents} aria-controls="results-pairs-list" className="font-medium text-primary hover:underline">
                  {showContents ? "Hide them" : "Show them"}
                </button>
              </p>
            )}
            {tab === "pairs" && (
              pairs.length === 0 ? (
                <p className="py-10 text-center text-sm text-text-muted">{structure ? "No label/value pairs were found." : "Reading the document's layout…"}</p>
              ) : (
                <ul id="results-pairs-list" aria-label="Key-value pairs" className="divide-y divide-border/70 overflow-hidden rounded-xl border border-border">
                  {pairs.filter((pair) => matches(pair.label, pair.value)).map((pair) => (
                    <li key={pair.id}>
                      <button
                        type="button"
                        onClick={() => select(pair)}
                        className={[
                          "grid w-full grid-cols-[minmax(0,2fr)_minmax(0,3fr)_9.5rem] items-center gap-3 px-3 py-2.5 text-left transition-colors",
                          selected?.id === pair.id ? "bg-primary-soft/60" : "hover:bg-surface-soft/70",
                        ].join(" ")}
                        data-testid="results-pair"
                      >
                        <span className="truncate text-sm text-text-secondary" title={pair.label}>{pair.label}</span>
                        <span className="break-words text-sm font-medium text-foreground">{pair.value}</span>
                        <span className="flex items-center justify-end gap-2 text-[11px] text-text-muted">
                          {pair.page ? <span className="tabular-nums">p.{pair.page}</span> : null}
                          {pair.quality !== null ? (
                            <span className="flex items-center gap-1" title={`Layout quality ${Math.round(pair.quality * 100)}%`}>
                              <span className="h-1.5 w-10 overflow-hidden rounded-full bg-surface-soft">
                                <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.round(pair.quality * 100)}%` }} />
                              </span>
                            </span>
                          ) : (
                            <span className="rounded bg-surface-soft px-1.5 py-0.5">text</span>
                          )}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )
            )}

            {tab === "tables" && (
              tables.length === 0 ? (
                <p className="py-10 text-center text-sm text-text-muted">No tables were found in this document.</p>
              ) : (
                <div className="space-y-3">
                  {tables.filter((table) => !table.blank).map((table) => (
                    <div key={table.id} onClick={() => select(table)} role="presentation">
                      <DataTable table={table} filter={needle} />
                    </div>
                  ))}
                  {blankTables.length > 0 && (
                    // Forms printed blank in the document (a regulation's fill-in
                    // tables): listed together, not as screens of "—".
                    <details className="rounded-xl border border-dashed border-border" data-testid="blank-tables">
                      <summary className="cursor-pointer px-3 py-2 text-sm text-text-secondary">
                        {blankTables.length} fill-in table{blankTables.length === 1 ? "" : "s"} printed blank in the document — headers only
                      </summary>
                      <ul className="divide-y divide-border/60 border-t border-border text-xs">
                        {blankTables.map((table) => (
                          <li key={table.id} className="px-3 py-1.5">
                            <button type="button" onClick={() => select(table)} className="text-left">
                              <span className="font-medium text-foreground">{table.title}</span>
                              <span className="text-text-muted"> · {table.headers.filter(Boolean).join(" | ") || "no headers"} · {table.rows.length} blank row{table.rows.length === 1 ? "" : "s"}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )
            )}

            {tab === "ocr" && (
              pages === null ? (
                <div className="flex justify-center py-10 text-text-muted"><Loader2 className="h-5 w-5 animate-spin" aria-label="Loading text" /></div>
              ) : (
                <div className="space-y-4">
                  {pages.filter((item) => matches(item.final_text || "")).map((item) => {
                    const ocr = item.extraction_method?.toLowerCase().includes("ocr");
                    return (
                      <article key={item.page_number} className="overflow-hidden rounded-xl border border-border">
                        <header className="flex items-center justify-between gap-2 bg-surface-soft/70 px-3 py-2 text-xs">
                          <button type="button" className="font-medium text-foreground hover:text-primary" onClick={() => setPage(item.page_number)}>
                            Page {item.page_number}
                          </button>
                          <span className="flex items-center gap-2 text-text-muted">
                            <span className={`rounded-full px-2 py-0.5 font-medium ${ocr ? "bg-warning/10 text-warning" : "bg-success/10 text-success"}`}>
                              {ocr ? "OCR" : "Native text"}
                            </span>
                            <span className="tabular-nums">{item.word_count.toLocaleString()} words</span>
                            <button
                              type="button"
                              className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-surface hover:text-foreground"
                              onClick={() => {
                                void navigator.clipboard?.writeText(item.final_text || "");
                                setCopied(item.page_number);
                              }}
                            >
                              <Copy className="h-3 w-3" aria-hidden="true" />
                              {copied === item.page_number ? "Copied" : "Copy"}
                            </button>
                          </span>
                        </header>
                        <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap break-words px-3 py-2.5 font-mono text-[12.5px] leading-6 text-foreground">
                          {item.final_text ? highlightMatches(item.final_text, filter.trim()) : <span className="text-text-muted">No text on this page.</span>}
                        </pre>
                      </article>
                    );
                  })}
                </div>
              )
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
