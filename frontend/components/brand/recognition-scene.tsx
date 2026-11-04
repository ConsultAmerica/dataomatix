"use client";

import styles from "./recognition-scene.module.css";

/**
 * Document-intelligence recognition scene — stacked pages, a scanning
 * frustum, field chips lighting up, and a structured result card.
 * Decorative only; brand navy / blue / orange. Still under reduced motion.
 */
export default function RecognitionScene({
  compact = false,
  className = "",
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={[styles.scene, compact ? styles.compact : "", className].filter(Boolean).join(" ")}
      aria-hidden="true"
    >
      <div className={styles.grid} />

      {/* Incoming formats */}
      <span className={`${styles.chip} ${styles.formatPdf}`}>PDF</span>
      <span className={`${styles.chip} ${styles.formatDoc}`}>DOCX</span>
      <span className={`${styles.chip} ${styles.formatImg}`}>PNG</span>

      {/* Stacked source pages */}
      <div className={styles.stack}>
        <div className={`${styles.page} ${styles.pageFar}`} />
        <div className={`${styles.page} ${styles.pageMid}`} />
        <div className={`${styles.page} ${styles.pageFront}`}>
          <span className={styles.line} style={{ width: "62%" }} />
          <span className={styles.line} style={{ width: "78%" }} />
          <span className={styles.line} style={{ width: "54%" }} />
          <span className={`${styles.zone} ${styles.zoneA}`} />
          <span className={`${styles.zone} ${styles.zoneB}`} />
          <span className={`${styles.zone} ${styles.zoneC}`} />
          <div className={styles.scanBeam} />
        </div>
      </div>

      {/* Wireframe scan cube + dashed frustum */}
      <div className={styles.sensor}>
        <svg viewBox="0 0 64 64" className={styles.sensorSvg} fill="none" aria-hidden="true">
          <rect x="18" y="4" width="28" height="22" rx="4" className={styles.sensorBox} />
          <path d="M24 12 h16 M32 12 v8" className={styles.sensorCross} />
          <path d="M18 26 L8 58" className={styles.sensorRay} />
          <path d="M46 26 L56 58" className={styles.sensorRay} />
          <path d="M22 26 L18 58" className={styles.sensorRay} />
          <path d="M42 26 L46 58" className={styles.sensorRay} />
        </svg>
      </div>

      {/* Recognized field labels */}
      <span className={`${styles.label} ${styles.labelContract}`}>Contract No.</span>
      <span className={`${styles.label} ${styles.labelDate}`}>Award Date</span>
      <span className={`${styles.label} ${styles.labelValue}`}>Total Value</span>
      <span className={`${styles.label} ${styles.labelTable}`}>Table</span>
      <span className={`${styles.label} ${styles.labelClause}`}>Clause</span>

      {/* Structured output card */}
      <div className={styles.result}>
        <span className={styles.resultTitle}>Extracted</span>
        <span className={styles.resultRow}>
          <i className={styles.check} />
          W912HQ-24-C-0001
        </span>
        <span className={styles.resultRow}>
          <i className={styles.check} />
          08/19/2026
        </span>
        <span className={styles.resultRow}>
          <i className={styles.check} />
          $1.25M
        </span>
      </div>
    </div>
  );
}
