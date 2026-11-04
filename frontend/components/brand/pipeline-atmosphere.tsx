"use client";

import {
  AnalyzeIcon,
  ExtractIcon,
  ProcessIcon,
  ReportIcon,
  TransformIcon,
} from "@/components/brand/capability-icons";

import styles from "./pipeline-atmosphere.module.css";

/**
 * Soft floating pipeline icons for PageHero backgrounds — extract → process
 * → transform → analyze → report. Decorative only; copy carries meaning.
 */
export default function PipelineAtmosphere({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`${styles.layer} ${compact ? styles.compact : ""}`} aria-hidden="true">
      <span className={`${styles.motif} ${styles.m1}`}>
        <ExtractIcon size={compact ? 44 : 56} animated />
      </span>
      <span className={`${styles.motif} ${styles.m2}`}>
        <ProcessIcon size={compact ? 40 : 48} animated />
      </span>
      <span className={`${styles.motif} ${styles.m3}`}>
        <TransformIcon size={compact ? 42 : 52} animated />
      </span>
      <span className={`${styles.motif} ${styles.m4}`}>
        <AnalyzeIcon size={48} animated />
      </span>
      <span className={`${styles.motif} ${styles.m5}`}>
        <ReportIcon size={52} animated />
      </span>
    </div>
  );
}
