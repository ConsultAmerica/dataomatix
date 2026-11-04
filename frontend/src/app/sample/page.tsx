import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, FileSearch, Upload } from "lucide-react";

import ContentSection from "@/components/layout/ContentSection";
import ConsoleHeader from "@/components/layout/ConsoleHeader";
import SampleContractViewer from "@/components/sample/sample-contract-viewer";

export const metadata: Metadata = {
  title: "Sample contract",
  description:
    "Open a sample federal contract and see every extracted value boxed on its source page, the fields routed to review, and the audit trail your decisions create.",
};

export default function SamplePage() {
  return (
    <div className="workspace-page w-full">
      <ConsoleHeader
        icon={FileSearch}
        title="Sample contract"
        description="A fictional SF 1449 award, run through the real extraction pipeline. Pick a field to see its source box, resolve review items, and watch the audit trail respond."
        actions={
          <>
            <Link href="/extraction/new" className="btn-primary inline-flex h-9 items-center gap-1.5 px-3.5 text-[13px]">
              <Upload className="h-4 w-4" />
              Try your own contract
            </Link>
            <Link href="/#confidence" className="btn-secondary inline-flex h-9 items-center gap-1.5 px-3.5 text-[13px]">
              How confidence works
              <ArrowRight className="h-4 w-4" />
            </Link>
          </>
        }
      />
      <ContentSection wide>
        <SampleContractViewer />
      </ContentSection>
    </div>
  );
}
