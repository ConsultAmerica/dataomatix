"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { ComponentType } from "react";

import {
  AnalyzeIcon,
  ExtractIcon,
  ProcessIcon,
  ReportIcon,
  TransformIcon,
} from "@/components/brand/capability-icons";

type Capability = {
  title: string;
  body: string;
  icon: ComponentType<{ size?: number; animated?: boolean }>;
  href?: string;
  action?: string;
};

/** What the product does, in pipeline order, with the brand icons. */
const CAPABILITIES: Capability[] = [
  {
    title: "Extract",
    body: "Fields, tables, clauses and form boxes read from every page, each one boxed where it is printed.",
    icon: ExtractIcon,
    href: "/extraction/new",
    action: "Start extraction",
  },
  {
    title: "Process",
    body: "Document type, schema and staging records built from what was read, never from guesses.",
    icon: ProcessIcon,
    href: "/classification",
    action: "See classification",
  },
  {
    title: "Transform",
    body: "One source fans into typed outputs — sections, tables and mapped fields ready for downstream systems.",
    icon: TransformIcon,
    href: "/documents",
    action: "Open documents",
  },
  {
    title: "Analyze",
    body: "Totals, dates and identifiers scored against the page; anything uncertain goes to a reviewer.",
    icon: AnalyzeIcon,
    href: "/analytics",
    action: "View analytics",
  },
  {
    title: "Report",
    body: "Verified values exported as structured sheets and review-ready records your ops team can trust.",
    icon: ReportIcon,
    href: "/review-queue",
    action: "Open review",
  },
];

export default function CapabilityBand() {
  return (
    <section className="marketing-band" aria-labelledby="capabilities-title" data-testid="capability-band">
      <div className="marketing-band-inner">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#b4530a]">How it works</p>
          <h2 id="capabilities-title" className="mt-2 text-balance text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            From a stack of pages to data you can trust
          </h2>
        </div>
        <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {CAPABILITIES.map((capability, index) => {
            const Icon = capability.icon;
            return (
              <li
                key={capability.title}
                className="group relative flex flex-col rounded-2xl border border-border bg-surface p-5 shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="flex items-center justify-between">
                  <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[linear-gradient(160deg,#eef5ff,#fff6ec)] ring-1 ring-[#dbe7fb]">
                    <Icon size={44} animated />
                  </span>
                  <span className="text-xs font-semibold tabular-nums text-text-muted" aria-hidden="true">
                    0{index + 1}
                  </span>
                </div>
                <h3 className="mt-4 text-lg font-semibold text-foreground">{capability.title}</h3>
                <p className="mt-1.5 flex-1 text-sm leading-relaxed text-text-secondary">{capability.body}</p>
                {capability.href && (
                  <Link
                    href={capability.href}
                    className="mt-4 inline-flex items-center gap-1.5 self-start rounded-md text-sm font-semibold text-[#1565d8] hover:text-[#0d47a8] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1565d8]"
                  >
                    {capability.action}
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                  </Link>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
