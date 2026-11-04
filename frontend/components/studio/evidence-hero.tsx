"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, ArrowUpRight, Check, CornerDownRight, UserRound } from "lucide-react";

import styles from "./evidence-hero.module.css";

/**
 * Home hero: the product's promise acted out in one loop. A scanner passes
 * over a (fictional) award page, each value is boxed where it was read, and
 * the value lands in the reviewed-data panel with its confidence. The one
 * value the agent can't trust is routed to a person instead of guessed.
 * One clock drives the scene so it builds and resets as a whole; reduced-motion
 * users get the finished state.
 */

type Field = {
  key: string;
  label: string;
  value: string;
  conf: number;
  page: string;
  review?: boolean;
};

const FIELDS: Field[] = [
  { key: "piid", label: "Contract number", value: "W91ZZZ26C0042", conf: 98, page: "p.1" },
  { key: "date", label: "Award date", value: "08/19/2026", conf: 96, page: "p.1" },
  { key: "vendor", label: "Contractor", value: "Northwind Analytics LLC", conf: 91, page: "p.1" },
  { key: "total", label: "Total award", value: "$1,250,000.00", conf: 97, page: "p.1" },
  { key: "issued", label: "Issued by", value: "2 candidates", conf: 50, page: "p.1", review: true },
];

const STEPS = FIELDS.length + 5; // fields, then the route card, then a hold

function useStep() {
  // Server render and reduced motion show the finished scene; the first tick
  // wraps the clock to 0 and the loop starts building.
  const [step, setStep] = useState(STEPS);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => setStep((s) => (s + 1) % (STEPS + 1)), 850);
    return () => window.clearInterval(id);
  }, []);
  return step;
}

export default function EvidenceHero() {
  const step = useStep();
  return (
    <section className={styles.hero} aria-labelledby="hero-title">
      <div className={styles.paperGrain} aria-hidden="true" />
      <div className={styles.inner}>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>
            <span className={styles.liveDot} aria-hidden="true" />
            Federal contract agents
          </p>
          <h1 id="hero-title" className={styles.title}>
            Extract with confidence.
            <br />
            <span className={styles.titleSoft}>
              Verify with <span className={styles.evidenceWord}>evidence</span>.
            </span>
          </h1>
          <p className={styles.lede}>
            Agents that read awards, solicitations and modifications. Every CLIN, funding line, clause and award
            field is boxed on its page, sent to a reviewer when it can&rsquo;t be trusted, and exported
            Oracle&#8209;ready.
          </p>
          <div className={styles.actions}>
            <Link href="/extraction/new" className={styles.primary}>
              Start extraction
              <ArrowRight className="h-4 w-4" strokeWidth={2} aria-hidden />
            </Link>
            <Link href="/sample" className={styles.secondary}>
              Open a sample contract
              <ArrowUpRight className="h-4 w-4" strokeWidth={2} aria-hidden />
            </Link>
          </div>
          <ul className={styles.proof}>
            <li>
              <Check className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden /> Boxed on the source page
            </li>
            <li>
              <Check className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden /> Unsure values go to a person
            </li>
            <li>
              <Check className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden /> Append-only audit trail
            </li>
          </ul>
        </div>

        <div className={styles.stage} aria-label="Illustration: an agent reading a fictional award page" role="img">
          {/* The source page: each value carries its own evidence box. */}
          <div className={styles.page} data-scanning={step < FIELDS.length + 1 ? "" : undefined}>
            <div className={styles.pageHead}>
              <span>AWARD / CONTRACT</span>
              <span className={styles.pageForm}>SF 1449 · p.1</span>
            </div>
            <div className={styles.pageBody}>
              <div className={styles.pageGrid}>
                <PageField label="1. Contract no." field={FIELDS[0]} shown={step > 0} />
                <PageField label="2. Award date" field={FIELDS[1]} shown={step > 1} />
              </div>
              <PageField label="17a. Contractor / offeror" field={FIELDS[2]} shown={step > 2} display="Northwind Analytics LLC" />
              <span className={styles.pageLine} style={{ width: "62%" }} />
              <span className={styles.pageLine} style={{ width: "48%" }} />
              <div className={styles.pageRule} />
              <PageField label="31. Total award amount" field={FIELDS[3]} shown={step > 3} strong />
              <PageField
                label="9. Issued by"
                field={FIELDS[4]}
                shown={step > 4}
                display={
                  <>
                    Army Contracting Cmd.
                    <br />
                    <span className={styles.pageValueAlt}>Mission &amp; Installation Contracting</span>
                  </>
                }
              />
              <div className={styles.pageLines} aria-hidden="true">
                <span style={{ width: "88%" }} />
                <span style={{ width: "72%" }} />
                <span style={{ width: "80%" }} />
              </div>
            </div>
            <div className={styles.scan} aria-hidden="true" />
          </div>

          {/* The reviewed data panel */}
          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <span className={styles.panelTitle}>Extracted fields</span>
              <span className={styles.panelBadge}>
                <span className={styles.panelPulse} aria-hidden="true" />
                Agent running
              </span>
            </div>
            <ol className={styles.rows}>
              {FIELDS.map((f, i) => (
                <li
                  key={f.key}
                  className={[styles.row, f.review ? styles.rowReview : ""].join(" ")}
                  data-shown={step > i ? "" : undefined}
                >
                  <span className={styles.rowLabel}>{f.label}</span>
                  <span className={styles.rowValue}>{f.value}</span>
                  <span className={styles.rowMeta}>
                    <span className={styles.conf}>
                      <span className={styles.confBar} style={{ width: `${f.conf}%` }} />
                    </span>
                    {f.page}
                  </span>
                </li>
              ))}
            </ol>
            <div className={styles.route} data-shown={step > FIELDS.length ? "" : undefined}>
              <CornerDownRight className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
              <span>
                <b>Issued by</b> routed to a reviewer · two plausible values
              </span>
              <span className={styles.routeWho}>
                <UserRound className="h-3 w-3" strokeWidth={2.2} aria-hidden />
                Contract specialist
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function PageField({
  label,
  field,
  shown,
  display,
  strong,
}: {
  label: string;
  field: Field;
  shown: boolean;
  display?: ReactNode;
  strong?: boolean;
}) {
  return (
    <div className={styles.pageField}>
      <span className={styles.pageLabel}>{label}</span>
      <span className={[styles.pageValue, strong ? styles.pageValueStrong : ""].join(" ")}>
        {display ?? field.value}
        <span
          className={[styles.box, field.review ? styles.boxReview : ""].join(" ")}
          data-shown={shown ? "" : undefined}
          aria-hidden="true"
        >
          <span className={styles.boxTag}>{field.review ? "50% · review" : `${field.conf}%`}</span>
        </span>
      </span>
    </div>
  );
}
