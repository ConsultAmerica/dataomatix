"use client";

import { useEffect, useState } from "react";
import { GitBranch } from "lucide-react";

import ContractHierarchy from "@/components/contract-hierarchy";
import DocumentResultsTable from "@/components/document-results-table";
import ConsoleHeader from "@/components/layout/ConsoleHeader";
import EmptyState from "@/components/ui/empty-state";
import { LoadingState } from "@/components/layout/StatusState";
import { getDocumentHierarchy, searchDocuments } from "@/lib/documents";
import type { DocumentSummary, HierarchyNode } from "@/types/document";

type ViewMode = "tree" | "table";

export default function RelationshipsPage() {
  const [view, setView] = useState<ViewMode>("tree");
  const [roots, setRoots] = useState<HierarchyNode[]>([]);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);

      try {
        const [hierarchy, search] = await Promise.all([
          getDocumentHierarchy(),
          searchDocuments({ limit: 50 }),
        ]);

        if (!active) return;
        setRoots(hierarchy.roots);
        setDocuments(
          search.documents.filter((doc) => Boolean(doc.relationship)),
        );
      } catch {
        if (active) {
          setRoots([]);
          setDocuments([]);
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
  }, []);

  const relatedCount = documents.length;

  return (
    <div className="workspace-page w-full">
      <ConsoleHeader
        icon={GitBranch}
        title="Contract relationships"
        description="Explore parent-child contract hierarchies and related documents."
        tabs={[
          {
            id: "tree",
            label: "Tree",
            active: view === "tree",
            onSelect: () => setView("tree"),
          },
          {
            id: "table",
            label: "Table",
            count: relatedCount,
            active: view === "table",
            onSelect: () => setView("table"),
          },
        ]}
        tabsLabel="Relationship views"
      />

      <div className="px-4 py-4 sm:px-6 sm:py-5">
        <div className="data-panel overflow-hidden">
          {loading ? (
            <LoadingState
              title="Detecting document relationships..."
              description="Analyzing parent-child contracts, SOWs, task orders, and amendment lineages."
            />
          ) : view === "tree" ? (
            roots.length > 0 ? (
              <ContractHierarchy roots={roots} />
            ) : (
              <EmptyState
                icon={GitBranch}
                title="No document relationships detected"
                description="Upload master agreements and related amendments to view contract trees and dependencies."
              />
            )
          ) : (
            <DocumentResultsTable
              documents={documents}
              emptyMessage="No related documents found."
              showExtendedColumns
            />
          )}
        </div>
      </div>
    </div>
  );
}
