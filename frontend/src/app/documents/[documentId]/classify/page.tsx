"use client";

import { useParams } from "next/navigation";

import ClassificationPanel from "@/components/classification/classification-panel";
import DocumentCapabilityShell from "@/components/documents/document-capability-shell";

export default function DocumentClassifyPage() {
  const { documentId } = useParams<{ documentId: string }>();
  return (
    <DocumentCapabilityShell documentId={documentId} active="classify">
      <div className="h-full overflow-auto">
        <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
          <h2 className="text-lg font-semibold text-foreground">Classification</h2>
          <p className="mt-1 text-sm text-text-secondary">
            The document&apos;s family, type and form, with the evidence for each. A decision here re-stages the document&apos;s extracted data.
          </p>
          <div className="mt-4 rounded-2xl border border-border bg-surface p-4 shadow-sm">
            <ClassificationPanel documentId={documentId} />
          </div>
        </div>
      </div>
    </DocumentCapabilityShell>
  );
}
