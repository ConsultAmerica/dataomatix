"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Loader2, Search } from "lucide-react";

import DocumentCapabilityShell from "@/components/documents/document-capability-shell";
import { getClauseOutline, type ClauseOutline } from "@/lib/clause-outline";

/** The document's numbered outline — sections, clauses and their
 * paragraphs, as printed — each opening its page in Parse. */
export default function DocumentSectionsPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const [outline, setOutline] = useState<ClauseOutline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let live = true;
    getClauseOutline(documentId)
      .then((result) => live && setOutline(result))
      .catch((reason: Error) => live && setError(reason.message || "The outline could not be loaded."));
    return () => {
      live = false;
    };
  }, [documentId]);

  const rows = useMemo(() => {
    if (!outline) return [];
    const heading = outline.columns.findIndex((column) => column.key === "heading");
    const needle = query.trim().toLowerCase();
    return outline.records
      .filter((record) => record.kind === "section" || record.kind === "clause")
      .map((record) => ({ ...record, heading: heading >= 0 ? record.cells[heading] : "" }))
      .filter((record) => !needle || `${record.number} ${record.heading}`.toLowerCase().includes(needle));
  }, [outline, query]);

  return (
    <DocumentCapabilityShell documentId={documentId} active="sections">
      <div className="h-full overflow-auto">
        <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Sections</h2>
              <p className="mt-1 text-sm text-text-secondary">Sections and clauses in document order, as printed. Open one to see it on its page.</p>
            </div>
            <label className="relative flex items-center">
              <span className="sr-only">Search sections</span>
              <Search className="pointer-events-none absolute left-2.5 h-4 w-4 text-text-muted" aria-hidden="true" />
              <input id="sections-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search number or title" className="h-9 w-60 rounded-md border border-border bg-surface pl-8 pr-2 text-sm" />
            </label>
          </div>
          {error ? (
            <p className="mt-6 text-sm text-danger" role="alert">{error}</p>
          ) : !outline ? (
            <p className="mt-6 flex items-center gap-2 text-sm text-text-secondary"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Reading the outline…</p>
          ) : outline.style === "none" ? (
            <p className="mt-6 rounded-xl border border-border bg-surface p-4 text-sm text-text-secondary">
              This document has no numbered sections or clauses. Its full content is on the Parse page.
            </p>
          ) : (
            <ol className="mt-5 divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface shadow-sm" data-testid="sections-list">
              {rows.map((row, index) => (
                <li key={`${row.number}-${index}`}>
                  <Link
                    href={`/documents/${documentId}/parse?page=${row.page_start}`}
                    className="flex items-baseline gap-3 px-4 py-2.5 text-sm hover:bg-surface-soft focus-visible:bg-surface-soft focus-visible:outline-none"
                    style={{ paddingLeft: `${1 + Math.max(0, row.level - 1) * 1.25}rem` }}
                  >
                    <span className={`shrink-0 tabular-nums ${row.kind === "section" ? "font-semibold text-[#0d47a8]" : "text-text-secondary"}`}>{row.number}</span>
                    <span className={`min-w-0 flex-1 ${row.kind === "section" ? "font-semibold text-foreground" : "text-foreground"}`}>{row.heading}</span>
                    <span className="shrink-0 text-xs text-text-muted">p. {row.page_start}</span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </DocumentCapabilityShell>
  );
}
