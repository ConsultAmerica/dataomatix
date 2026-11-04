"use client";

import { Suspense } from "react";
import { Zap } from "lucide-react";

import ActionCatalog from "@/components/actions/action-catalog";
import ContentSection from "@/components/layout/ContentSection";
import ConsoleHeader from "@/components/layout/ConsoleHeader";

export default function ActionsPage() {
  return (
    <div className="workspace-page w-full">
      <ConsoleHeader
        icon={Zap}
        title="Agent actions"
        description="One-click reports over a document — executive summary, risk register, clause gaps, obligations and funding — built only from extracted, source-cited data."
      />
      <ContentSection>
        <Suspense fallback={null}>
          <ActionCatalog />
        </Suspense>
      </ContentSection>
    </div>
  );
}
