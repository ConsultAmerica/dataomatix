"use client";

import {
  AnalyzeIcon,
  ExtractIcon,
  ProcessIcon,
  ReportIcon,
  TransformIcon,
} from "@/components/brand/capability-icons";
import RecognitionScene from "@/components/brand/recognition-scene";

import styles from "./pipeline-atmosphere.module.css";

/**
 * PageHero background: document-intelligence recognition scene plus soft
 * floating pipeline icons. Decorative only; copy carries meaning.
 */
export default function PipelineAtmosphere({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={`${styles.layer} ${compact ? styles.compact : ""}`}
      data-pipeline-atmosphere
      aria-hidden="true"
    >
      <div className={styles.sceneWrap}>
        <RecognitionScene compact={compact} />
      </div>

      <span className={`${styles.motif} ${styles.m1}`}>
        <ExtractIcon size={compact ? 40 : 48} animated />
      </span>
      <span className={`${styles.motif} ${styles.m2}`}>
        <ProcessIcon size={compact ? 36 : 42} animated />
      </span>
      {!compact && (
        <>
          <span className={`${styles.motif} ${styles.m3}`}>
            <TransformIcon size={44} animated />
          </span>
          <span className={`${styles.motif} ${styles.m4}`}>
            <AnalyzeIcon size={40} animated />
          </span>
          <span className={`${styles.motif} ${styles.m5}`}>
            <ReportIcon size={44} animated />
          </span>
        </>
      )}
    </div>
  );
}
