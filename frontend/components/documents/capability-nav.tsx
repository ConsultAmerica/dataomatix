"use client";

import Link from "next/link";
import { FileSearch, LayoutGrid, ListTree, ScanLine, Scissors } from "lucide-react";

export type Capability = "parse" | "extract" | "classify" | "sections" | "split";

/** One page per capability: Parse (the document as read), Extract (fields
 * and records — the existing workspace), Classify, Sections and Split. */
export const CAPABILITIES: { id: Capability; label: string; icon: typeof ScanLine; path: string }[] = [
  { id: "parse", label: "Parse", icon: ScanLine, path: "/parse" },
  { id: "extract", label: "Extract", icon: FileSearch, path: "" },
  { id: "classify", label: "Classify", icon: LayoutGrid, path: "/classify" },
  { id: "sections", label: "Sections", icon: ListTree, path: "/sections" },
  { id: "split", label: "Split", icon: Scissors, path: "/split" },
];

export function capabilityHref(documentId: string, capability: Capability): string {
  return `/documents/${documentId}${CAPABILITIES.find((item) => item.id === capability)!.path}`;
}

export default function CapabilityNav({ documentId, active }: { documentId: string; active: Capability }) {
  return (
    <nav aria-label="Document capabilities" className="-mb-px flex min-w-0 overflow-x-auto" data-testid="capability-nav">
      <ul className="flex min-w-max items-end gap-1">
        {CAPABILITIES.map(({ id, label, icon: Icon }) => {
          const current = id === active;
          return (
            <li key={id}>
              <Link
                href={capabilityHref(documentId, id)}
                aria-current={current ? "page" : undefined}
                className={[
                  "flex h-10 items-center gap-2 rounded-t-xl border px-4 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary sm:px-5",
                  current
                    ? "border-border border-b-surface bg-surface font-semibold text-foreground"
                    : "border-transparent bg-surface-soft/70 text-text-secondary hover:bg-surface-soft hover:text-foreground",
                ].join(" ")}
              >
                <span
                  className={[
                    "flex h-6 w-6 items-center justify-center rounded-md",
                    current ? "bg-[#e8f1fe] text-[#1565d8]" : "text-text-muted",
                  ].join(" ")}
                  aria-hidden="true"
                >
                  <Icon className="h-4 w-4" strokeWidth={1.75} />
                </span>
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
