"use client";

import { Suspense } from "react";
import { GitCompareArrows } from "lucide-react";

import DocumentCompare from "@/components/compare/document-compare";
import ContentSection from "@/components/layout/ContentSection";
import ConsoleHeader from "@/components/layout/ConsoleHeader";

export default function ComparePage() {
  return (
    <div className="workspace-page w-full">
      <ConsoleHeader
        icon={GitCompareArrows}
        title="Compare documents"
        description="Put a modification next to its base award — or any two documents — and see which fields, CLINs, funding lines and clauses were added, removed or changed."
      />
      <ContentSection>
        <Suspense>
          <DocumentCompare />
        </Suspense>
      </ContentSection>
    </div>
  );
}
