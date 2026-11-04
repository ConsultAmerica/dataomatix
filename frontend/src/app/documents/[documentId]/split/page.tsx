"use client";

import { useParams } from "next/navigation";

import { SplitIcon } from "@/components/brand/capability-icons";
import DocumentCapabilityShell from "@/components/documents/document-capability-shell";
import RelatedDocumentsSwitcher from "@/components/documents/related-documents-switcher";

/** Split: package splitting is not built yet, so this page says so and
 * shows what exists today — the documents linked to this one. */
export default function DocumentSplitPage() {
  const { documentId } = useParams<{ documentId: string }>();
  return (
    <DocumentCapabilityShell documentId={documentId} active="split">
      <div className="h-full overflow-auto">
        <div className="mx-auto max-w-2xl px-4 py-10 text-center sm:px-6">
          <span className="mx-auto flex h-20 w-20 items-center justify-center rounded-3xl bg-[linear-gradient(160deg,#eef5ff,#fff6ec)] ring-1 ring-[#dbe7fb]">
            <SplitIcon size={56} animated />
          </span>
          <h2 className="mt-5 text-xl font-semibold text-foreground">Splitting packages is in development</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-text-secondary">
            When it&apos;s ready, a package will be separated into its child documents by page range, each with its own type and fields.
            Nothing here has been split, and no page ranges are suggested yet.
          </p>
          <div className="mx-auto mt-8 max-w-md rounded-2xl border border-border bg-surface p-4 text-left shadow-sm">
            <h3 className="text-sm font-semibold text-foreground">Related documents</h3>
            <p className="mt-1 text-xs text-text-secondary">Contracts, modifications and other documents linked to this one.</p>
            <div className="mt-3">
              <RelatedDocumentsSwitcher documentId={documentId} />
            </div>
          </div>
        </div>
      </div>
    </DocumentCapabilityShell>
  );
}
