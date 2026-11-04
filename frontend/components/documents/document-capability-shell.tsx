"use client";

import { FileText } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import CapabilityNav, { type Capability } from "@/components/documents/capability-nav";
import { useDocumentChrome } from "@/components/layout/document-chrome-context";
import { getDocument } from "@/lib/documents";

/** The frame every capability page shares: the file, the five
 * capabilities, and the page's own controls on the right. The app's
 * breadcrumb (Workspace › Documents › file › page) names the file too.
 * The page body fills the rest of the screen. */
export default function DocumentCapabilityShell({
  documentId,
  active,
  filename,
  controls,
  children,
}: {
  documentId: string;
  active: Capability;
  /** Known already (Parse returns it); otherwise read from the document. */
  filename?: string | null;
  controls?: ReactNode;
  children: ReactNode;
}) {
  const [name, setName] = useState<string | null>(filename ?? null);
  const { setDocumentTitle } = useDocumentChrome();
  const title = name ?? filename ?? null;

  useEffect(() => {
    setDocumentTitle(title);
    return () => setDocumentTitle(null);
  }, [title, setDocumentTitle]);

  useEffect(() => {
    if (filename) return;
    let live = true;
    getDocument(documentId)
      .then((document) => live && setName(document.original_filename))
      .catch(() => live && setName(null));
    return () => {
      live = false;
    };
  }, [documentId, filename]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--color-page)]" data-testid={`capability-page-${active}`}>
      <div className="border-b border-border bg-surface px-4 pt-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
          <h1 className="flex min-w-0 items-center gap-2 text-base font-semibold text-foreground">
            <FileText className="h-4 w-4 shrink-0 text-[#1565d8]" aria-hidden="true" />
            <span className="truncate" data-testid="capability-filename">{title ?? "Document"}</span>
          </h1>
          {controls && <div className="flex flex-wrap items-center gap-2">{controls}</div>}
        </div>
        <CapabilityNav documentId={documentId} active={active} />
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
