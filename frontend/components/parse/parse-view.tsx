"use client";

import {
  AlertTriangle,
  Braces,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  Minus,
  Plus,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import DocumentCapabilityShell from "@/components/documents/document-capability-shell";
import { getPageRender } from "@/lib/documents";
import { downloadBlob } from "@/lib/export";
import {
  BLOCK_LABELS,
  downloadParse,
  getParse,
  pageMarkdown,
  type BlockType,
  type ParseBlock,
  type ParsePage,
  type ParseResult,
} from "@/lib/parse";
import { useWindowedRows } from "@/lib/use-windowed-rows";
import type { PageRender } from "@/types/document";

/** One colour per block type, used for the box on the page and the chip on
 * its card, so the two read as the same thing. */
const TYPE_STYLE: Record<BlockType, { box: string; chip: string }> = {
  heading: { box: "border-[#1565d8] bg-[#1565d8]/10", chip: "bg-[#e8f1fe] text-[#0d47a8]" },
  paragraph: { box: "border-[#1f9d6b] bg-[#1f9d6b]/10", chip: "bg-[#e3f5ec] text-[#11603f]" },
  table: { box: "border-[#6554c0] bg-[#6554c0]/10", chip: "bg-[#eeebfa] text-[#4a3a9e]" },
  header: { box: "border-[#64748b] bg-[#64748b]/10", chip: "bg-[#eef2f6] text-[#475569]" },
  footer: { box: "border-[#64748b] bg-[#64748b]/10", chip: "bg-[#eef2f6] text-[#475569]" },
  page_reference: { box: "border-[#64748b] bg-[#64748b]/10", chip: "bg-[#eef2f6] text-[#475569]" },
  marginalia: { box: "border-[#c2570a] bg-[#f7931e]/10", chip: "bg-[#fff1e3] text-[#9a4a06]" },
};

type Tab = "markdown" | "json";
type Pane = "document" | "content";

function usePage(documentId: string, total: number | null) {
  const router = useRouter();
  const params = useSearchParams();
  const requested = Number(params.get("page") ?? "1");
  const page = Number.isFinite(requested) && requested >= 1 ? Math.min(requested, total ?? requested) : 1;
  const go = useCallback(
    (next: number) => router.replace(`/documents/${documentId}/parse?page=${next}`, { scroll: false }),
    [documentId, router],
  );
  return [page, go] as const;
}

export default function ParseView({ documentId }: { documentId: string }) {
  const [meta, setMeta] = useState<ParseResult | null>(null);
  const [pages, setPages] = useState<Record<number, ParsePage>>({});
  const [renders, setRenders] = useState<Record<number, PageRender | "unavailable">>({});
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("markdown");
  const [query, setQuery] = useState("");
  const [type, setType] = useState<BlockType | "all">("all");
  const [zoom, setZoom] = useState(1);
  const [pane, setPane] = useState<Pane>("content");
  const [page, goToPage] = usePage(documentId, meta?.document.page_count ?? null);
  const [exporting, setExporting] = useState<"xlsx" | "csv" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const loading = useRef(new Set<number>());

  // The parsed page (and its neighbour, so turning the page is instant).
  const load = useCallback(
    (number: number) => {
      if (loading.current.has(number)) return;
      loading.current.add(number);
      getParse(documentId, number, 1)
        .then((result) => {
          setMeta((current) => current ?? result);
          setPages((current) => ({ ...current, ...Object.fromEntries(result.pages.map((p) => [p.page_number, p])) }));
        })
        .catch((reason: Error) => {
          loading.current.delete(number);
          setError(reason.message || "The parsed content could not be loaded.");
        });
    },
    [documentId],
  );

  useEffect(() => {
    load(page);
    if (meta && page < meta.document.page_count) load(page + 1);
  }, [load, meta, page]);

  // The page image, rendered by the backend from the stored file.
  useEffect(() => {
    if (!meta || meta.document.source_type === "html" || renders[page]) return;
    let live = true;
    getPageRender(documentId, page)
      .then((render) => live && setRenders((current) => ({ ...current, [page]: render })))
      .catch(() => live && setRenders((current) => ({ ...current, [page]: "unavailable" })));
    return () => {
      live = false;
    };
  }, [documentId, meta, page, renders]);

  const current = pages[page];
  const total = meta?.document.page_count ?? 0;
  const blocks = useMemo(() => {
    const all = current?.blocks ?? [];
    const needle = query.trim().toLowerCase();
    return all.filter((block) => (type === "all" || block.type === type) && (!needle || block.text.toLowerCase().includes(needle)));
  }, [current, query, type]);
  const types = useMemo(() => Array.from(new Set((current?.blocks ?? []).map((block) => block.type))), [current]);

  const turn = (next: number) => {
    if (next < 1 || next > total) return;
    setSelected(null);
    goToPage(next);
  };

  const copyText = tab === "json" ? JSON.stringify(current ?? null, null, 2) : current ? pageMarkdown(current) : "";
  const download = () => {
    if (!current || !meta) return;
    const base = (meta.document.filename || "document").replace(/\.[^.]+$/, "");
    downloadBlob(copyText, `${base}-page-${page}.${tab === "json" ? "json" : "md"}`, tab === "json" ? "application/json" : "text/markdown");
  };

  const exportFile = (format: "xlsx" | "csv") => {
    if (!meta) return;
    setExporting(format);
    setExportError(null);
    downloadParse(documentId, format, meta.document.filename || "document")
      .catch((reason: Error) => setExportError(reason.message || "The download failed."))
      .finally(() => setExporting(null));
  };

  const controls = meta && (
    <>
    {(["xlsx", "csv"] as const).map((format) => (
      <button
        key={format}
        type="button"
        className="btn-secondary inline-flex items-center gap-1.5 px-2.5 py-1 text-sm"
        disabled={exporting !== null}
        onClick={() => exportFile(format)}
        aria-label={`Download the parsed document as ${format === "xlsx" ? "Excel" : "CSV"}`}
      >
        {exporting === format ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />}
        {format === "xlsx" ? "Excel" : "CSV"}
      </button>
    ))}
    <div className="flex items-center gap-1 rounded-lg border border-border bg-surface px-1 py-0.5 text-sm" data-testid="parse-pager">
      <button type="button" className="rounded p-1.5 text-text-secondary hover:bg-surface-soft disabled:opacity-40" onClick={() => turn(page - 1)} disabled={page <= 1} aria-label="Previous page">
        <ChevronLeft className="h-4 w-4" />
      </button>
      <span className="min-w-[4.5rem] text-center tabular-nums text-foreground" aria-live="polite">
        {page} / {total}
      </span>
      <button type="button" className="rounded p-1.5 text-text-secondary hover:bg-surface-soft disabled:opacity-40" onClick={() => turn(page + 1)} disabled={page >= total} aria-label="Next page">
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
    </>
  );

  return (
    <DocumentCapabilityShell documentId={documentId} active="parse" filename={meta?.document.filename} controls={controls}>
      {exportError && <p className="border-b border-border bg-surface px-4 py-2 text-sm text-danger" role="alert">{exportError}</p>}
      {error && !current ? (
        <p className="m-6 rounded-lg border border-border bg-surface p-4 text-sm text-danger" role="alert">{error}</p>
      ) : !current || !meta ? (
        <div className="flex h-full items-center justify-center gap-2 text-sm text-text-secondary">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Reading the parsed document…
        </div>
      ) : (
        <div className="flex h-full min-h-0 flex-col">
          {/* Phones: one pane at a time. */}
          <div className="flex gap-1 border-b border-border bg-surface px-4 py-2 lg:hidden" role="tablist" aria-label="Pane">
            {(["document", "content"] as Pane[]).map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={pane === value}
                onClick={() => setPane(value)}
                className={`flex-1 rounded-md px-3 py-1.5 text-sm ${pane === value ? "bg-[#e8f1fe] font-semibold text-[#0d47a8]" : "text-text-secondary"}`}
              >
                {value === "document" ? "Document" : "Parsed content"}
              </button>
            ))}
          </div>
          <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
            <section
              aria-label="Original document"
              className={`${pane === "document" ? "flex" : "hidden"} min-h-0 flex-col border-r border-border bg-[#f3f5f8] lg:flex`}
            >
              <SourcePane
                page={current}
                render={renders[page]}
                sourceType={meta.document.source_type}
                zoom={zoom}
                onZoom={setZoom}
                selected={selected}
                onSelect={(id) => {
                  setSelected(id);
                  setPane("content");
                }}
              />
            </section>
            <section aria-label="Parsed content" className={`${pane === "content" ? "flex" : "hidden"} min-h-0 flex-col bg-surface lg:flex`}>
              <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
                <div className="flex rounded-lg bg-surface-soft p-0.5" role="tablist" aria-label="Format">
                  {([
                    ["markdown", "Markdown", FileText],
                    ["json", "JSON", Braces],
                  ] as const).map(([value, label, Icon]) => (
                    <button
                      key={value}
                      type="button"
                      role="tab"
                      aria-selected={tab === value}
                      onClick={() => setTab(value)}
                      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm ${tab === value ? "bg-surface font-semibold text-foreground shadow-sm" : "text-text-secondary hover:text-foreground"}`}
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                      {label}
                    </button>
                  ))}
                </div>
                <label className="relative ml-auto flex min-w-0 items-center">
                  <span className="sr-only">Search this page</span>
                  <Search className="pointer-events-none absolute left-2.5 h-4 w-4 text-text-muted" aria-hidden="true" />
                  <input
                    id="parse-search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search this page"
                    className="h-8 w-40 rounded-md border border-border bg-surface pl-8 pr-2 text-sm sm:w-48"
                  />
                </label>
                <label className="flex items-center">
                  <span className="sr-only">Block type</span>
                  <select
                    id="parse-type"
                    value={type}
                    onChange={(event) => setType(event.target.value as BlockType | "all")}
                    className="h-8 rounded-md border border-border bg-surface px-2 text-sm"
                  >
                    <option value="all">All types</option>
                    {types.map((value) => (
                      <option key={value} value={value}>{BLOCK_LABELS[value]}</option>
                    ))}
                  </select>
                </label>
                <button type="button" className="rounded-md p-1.5 text-text-secondary hover:bg-surface-soft" aria-label={`Copy page ${page} as ${tab === "json" ? "JSON" : "Markdown"}`} onClick={() => navigator.clipboard?.writeText(copyText).catch(() => {})}>
                  <Copy className="h-4 w-4" />
                </button>
                <button type="button" className="rounded-md p-1.5 text-text-secondary hover:bg-surface-soft" aria-label={`Download page ${page} as ${tab === "json" ? "JSON" : "Markdown"}`} onClick={download}>
                  <Download className="h-4 w-4" />
                </button>
              </div>
              <PageNotes page={current} meta={meta} />
              {tab === "markdown" ? (
                <BlockList blocks={blocks} selected={selected} onSelect={(id) => { setSelected(id); setPane("document"); }} />
              ) : (
                <pre tabIndex={0} aria-label="Page as JSON" className="min-h-0 flex-1 overflow-auto bg-[#0f172a] p-4 text-xs leading-relaxed text-[#e2e8f0] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#1565d8]" data-testid="parse-json">
                  {copyText}
                </pre>
              )}
            </section>
          </div>
        </div>
      )}
    </DocumentCapabilityShell>
  );
}

function PageNotes({ page, meta }: { page: ParsePage; meta: ParseResult }) {
  const notes: string[] = [];
  if (page.positioning !== "spatial") notes.push("This page has no word positions in its source: blocks are listed in order, without boxes on the page.");
  if (!page.completeness.complete) notes.push(`${page.completeness.missing_characters} printed characters on this page are not in any block (${page.completeness.missing_tokens.slice(0, 5).join(", ")}).`);
  if (page.completeness.tables_with_cell_gaps) notes.push("A table's cells did not hold every printed word; the table's own words are shown under it.");
  if (meta.masking.applied) notes.push("Identifier numbers are masked for your role.");
  for (const warning of meta.warnings) notes.push(warning);
  if (!notes.length) return null;
  return (
    <ul className="space-y-1 border-b border-border bg-[#fffaf2] px-4 py-2 text-xs text-[#7a4a08]" data-testid="parse-notes">
      {notes.map((note) => (
        <li key={note} className="flex gap-1.5">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {note}
        </li>
      ))}
    </ul>
  );
}

function SourcePane({
  page,
  render,
  sourceType,
  zoom,
  onZoom,
  selected,
  onSelect,
}: {
  page: ParsePage;
  render: PageRender | "unavailable" | undefined;
  sourceType: string;
  zoom: number;
  onZoom: (zoom: number) => void;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const width = typeof render === "object" ? render.page_width : page.width;
  const height = typeof render === "object" ? render.page_height : page.height;

  // Keep the selected box in view.
  useEffect(() => {
    if (!selected) return;
    scroller.current?.querySelector<HTMLElement>(`[data-box="${selected}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selected]);

  return (
    <>
      <div className="flex items-center justify-end gap-1 border-b border-border bg-surface px-3 py-1.5 text-xs text-text-secondary">
        <button type="button" className="rounded p-1 hover:bg-surface-soft" aria-label="Zoom out" onClick={() => onZoom(Math.max(0.6, +(zoom - 0.2).toFixed(1)))}>
          <Minus className="h-3.5 w-3.5" />
        </button>
        <span className="w-10 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
        <button type="button" className="rounded p-1 hover:bg-surface-soft" aria-label="Zoom in" onClick={() => onZoom(Math.min(2.4, +(zoom + 0.2).toFixed(1)))}>
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button type="button" className="ml-1 rounded px-2 py-1 hover:bg-surface-soft" onClick={() => onZoom(1)}>
          Fit width
        </button>
      </div>
      <div ref={scroller} tabIndex={0} aria-label="Page image" className="min-h-0 flex-1 overflow-auto p-4 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#1565d8]" data-testid="parse-source">
        {sourceType === "html" ? (
          <p className="mx-auto max-w-md rounded-lg border border-border bg-surface p-4 text-sm text-text-secondary">
            This is an HTML document: it has no pages to draw. Its blocks are listed in source order on the right.
          </p>
        ) : render === undefined ? (
          <div className="flex h-full items-center justify-center text-sm text-text-secondary">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> Rendering page {page.page_number}…
          </div>
        ) : render === "unavailable" || !width || !height ? (
          <p className="mx-auto max-w-md rounded-lg border border-border bg-surface p-4 text-sm text-text-secondary">
            The page image isn&apos;t available for this file type. Its parsed blocks are listed on the right.
          </p>
        ) : (
          <div className="relative mx-auto bg-white shadow-sm ring-1 ring-black/5" style={{ width: `${zoom * 100}%`, maxWidth: zoom === 1 ? 820 : undefined }}>
            {/* eslint-disable-next-line @next/next/no-img-element -- a data URL rendered by the backend */}
            <img src={render.image_data_url} alt={`Page ${page.page_number}`} className="block h-auto w-full select-none" draggable={false} />
            {page.blocks.map((block, number) =>
              block.bbox ? (
                <button
                  key={block.id}
                  type="button"
                  data-box={block.id}
                  aria-label={`Block ${number + 1}, ${BLOCK_LABELS[block.type]}`}
                  aria-pressed={selected === block.id}
                  onClick={() => onSelect(block.id)}
                  className={[
                    "absolute rounded-[2px] border transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#1565d8]",
                    selected === block.id
                      ? "border-2 border-[#1f9d6b] bg-[#1f9d6b]/15 ring-2 ring-[#1f9d6b]/40"
                      : `${TYPE_STYLE[block.type].box} opacity-75 hover:opacity-100`,
                  ].join(" ")}
                  style={{
                    left: `${(block.bbox[0] / width) * 100}%`,
                    top: `${(block.bbox[1] / height) * 100}%`,
                    width: `${((block.bbox[2] - block.bbox[0]) / width) * 100}%`,
                    height: `${((block.bbox[3] - block.bbox[1]) / height) * 100}%`,
                  }}
                >
                  {selected === block.id && (
                    <span className={`absolute -top-5 left-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold ${TYPE_STYLE[block.type].chip}`}>
                      {number + 1} · {BLOCK_LABELS[block.type]}
                    </span>
                  )}
                </button>
              ) : null,
            )}
          </div>
        )}
      </div>
    </>
  );
}

function BlockList({ blocks, selected, onSelect }: { blocks: ParseBlock[]; selected: string | null; onSelect: (id: string) => void }) {
  const [ref, view] = useWindowedRows(blocks.length, 96);

  // A block picked on the page scrolls into view here.
  useEffect(() => {
    const box = ref.current;
    if (!box || !selected) return;
    const index = blocks.findIndex((block) => block.id === selected);
    if (index < 0) return;
    const show = () => box.querySelector<HTMLElement>(`[data-block="${selected}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    if (!box.querySelector(`[data-block="${selected}"]`) && view.windowed) {
      box.scrollTop = index * (box.scrollHeight / Math.max(blocks.length, 1));
      requestAnimationFrame(() => requestAnimationFrame(show));
    } else {
      show();
    }
    // Only when the selection changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  if (!blocks.length) {
    return <p className="p-6 text-sm text-text-secondary">No blocks match on this page.</p>;
  }
  return (
    <div ref={ref} className="min-h-0 flex-1 overflow-auto px-4 py-3" data-testid="parse-blocks">
      {view.before > 0 && <div style={{ height: view.before }} aria-hidden="true" />}
      <ol className="space-y-2.5">
        {blocks.slice(view.start, view.end).map((block) => (
          <BlockCard key={block.id} block={block} active={selected === block.id} onSelect={onSelect} />
        ))}
      </ol>
      {view.after > 0 && <div style={{ height: view.after }} aria-hidden="true" />}
    </div>
  );
}

function BlockCard({ block, active, onSelect }: { block: ParseBlock; active: boolean; onSelect: (id: string) => void }) {
  const style = TYPE_STYLE[block.type];
  return (
    <li data-window-row data-block={block.id}>
      <button
        type="button"
        onClick={() => onSelect(block.id)}
        aria-pressed={active}
        className={[
          "w-full rounded-xl border bg-surface p-3 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#1565d8]",
          active ? "border-[#1f9d6b] ring-2 ring-[#1f9d6b]/25" : "border-border hover:border-[#9db8e0]",
        ].join(" ")}
      >
        <span className="flex items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${style.chip}`}>
            {block.index + 1} · {BLOCK_LABELS[block.type]}
          </span>
          {!block.bbox && <span className="text-[11px] text-text-muted">page only</span>}
        </span>
        {block.type === "table" && block.table ? (
          <TableBlock block={block} />
        ) : (
          <span
            className={`mt-1.5 block whitespace-pre-wrap break-words text-[15px] leading-relaxed text-foreground ${block.type === "heading" ? "font-semibold" : ""}`}
          >
            {block.text}
          </span>
        )}
        {block.lines.some((line) => line.raw_text) && (
          <span className="mt-1 block text-xs text-text-muted">
            As printed: {block.lines.map((line) => line.raw_text ?? line.text).join(" ")}
          </span>
        )}
      </button>
    </li>
  );
}

function TableBlock({ block }: { block: ParseBlock }) {
  const table = block.table!;
  return (
    <span className="mt-2 block overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        {table.headers.length > 0 && (
          <thead>
            <tr>
              {table.headers.map((header, index) => (
                <th key={index} className="border border-border bg-surface-soft px-2 py-1 text-left font-semibold">{header}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="border border-border px-2 py-1 align-top">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {table.source_lines && (
        <span className="mt-2 block rounded-md bg-[#fffaf2] p-2 text-xs text-[#7a4a08]">
          <span className="font-semibold">Printed in this table, not all in its cells:</span>
          <span className="mt-1 block whitespace-pre-wrap">{table.source_lines.join("\n")}</span>
        </span>
      )}
    </span>
  );
}

