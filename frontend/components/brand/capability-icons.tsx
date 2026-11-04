"use client";

import { useId, type ReactNode } from "react";

import styles from "./capability-icons.module.css";

/**
 * Brand icons for the document pipeline — Extract, Process, Transform,
 * Analyze, Report, Verify, Split — in the logo's navy, blue and orange.
 * Each has one small motion (`animated`), still under reduced motion;
 * without it they show their finished state. Decorative: the label beside
 * them says what they mean.
 */

type IconProps = { size?: number; animated?: boolean; className?: string };

const NAVY = "#0b2a5b";
const BLUE = "#1d63d1";
const SKY = "#2f86f0";
const ORANGE = "#f7931e";

function Frame({ size = 48, animated = false, className, children }: IconProps & { children: (id: string) => ReactNode }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      viewBox="0 0 48 48"
      width={size}
      height={size}
      fill="none"
      aria-hidden="true"
      className={[styles.icon, animated ? styles.animated : "", className].filter(Boolean).join(" ")}
    >
      <defs>
        <linearGradient id={`${id}-o`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffb547" />
          <stop offset="1" stopColor="#f26b0a" />
        </linearGradient>
        <linearGradient id={`${id}-b`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={SKY} />
          <stop offset="1" stopColor="#0d47a8" />
        </linearGradient>
      </defs>
      {children(id)}
    </svg>
  );
}

/** A page with an orange folded corner, as in the logo. */
function Page({ x, y, w, h, id }: { x: number; y: number; w: number; h: number; id: string }) {
  const fold = 6;
  return (
    <>
      <path
        d={`M${x + 2} ${y} H${x + w - fold} L${x + w} ${y + fold} V${y + h - 2} a2 2 0 0 1 -2 2 H${x + 2} a2 2 0 0 1 -2 -2 V${y + 2} a2 2 0 0 1 2 -2 Z`}
        fill="#ffffff"
        stroke={BLUE}
        strokeWidth="1.6"
      />
      <path d={`M${x + w - fold} ${y} L${x + w} ${y + fold} H${x + w - fold + 1} a1 1 0 0 1 -1 -1 Z`} fill={`url(#${id}-o)`} />
    </>
  );
}

/** Extract: scan frustum over a page; field chips light as the bar sweeps. */
export function ExtractIcon(props: IconProps) {
  return (
    <Frame {...props}>
      {(id) => (
        <>
          <rect x="10" y="10" width="22" height="30" rx="2.5" fill={`url(#${id}-b)`} opacity="0.18" />
          <Page x={11} y={8} w={20} h={30} id={id} />
          <g fill={NAVY} opacity="0.55">
            <rect x="14.5" y="14" width="9" height="1.6" rx="0.8" />
            <rect x="14.5" y="18" width="12" height="1.6" rx="0.8" />
            <rect x="14.5" y="22" width="8" height="1.6" rx="0.8" />
          </g>
          {/* Wireframe scan cube — Docsumo-style frustum, brand colors */}
          <g className={styles.frustum} stroke={SKY} strokeWidth="1.3" strokeDasharray="2.2 1.8" strokeLinecap="round">
            <path d="M34 6 L31 12" />
            <path d="M42 6 L39 12" />
            <path d="M34 14 L31 20" />
            <path d="M42 14 L39 20" />
            <rect x="33" y="4" width="10" height="10" rx="1.5" fill="#ffffff" stroke={BLUE} strokeWidth="1.4" strokeDasharray="none" />
            <path d="M36 7 h4 M38 7 v4" stroke={ORANGE} strokeWidth="1.4" strokeDasharray="none" />
          </g>
          <g className={styles.chip}>
            <rect x="33" y="24" width="12" height="5" rx="1.5" fill="#e8f1fe" stroke={SKY} strokeWidth="1" />
            <rect x="35" y="25.7" width="8" height="1.5" rx="0.6" fill={SKY} opacity="0.85" />
          </g>
          <g className={styles.chipDelay}>
            <rect x="33" y="31" width="12" height="5" rx="1.5" fill="#fff1e3" stroke={ORANGE} strokeWidth="1" />
            <rect x="35" y="32.7" width="7" height="1.5" rx="0.6" fill={ORANGE} opacity="0.9" />
          </g>
          <rect className={styles.scan} x="12" y="10" width="18" height="2.6" rx="1.3" fill={SKY} opacity="0.9" />
        </>
      )}
    </Frame>
  );
}

/** Process: orange feed into a turning gear holding structured data. */
export function ProcessIcon(props: IconProps) {
  const teeth = Array.from({ length: 8 }, (_, index) => index * 45);
  return (
    <Frame {...props}>
      {(id) => (
        <>
          <g className={styles.feed}>
            <rect x="2" y="21" width="11" height="5.5" rx="2.75" fill={`url(#${id}-o)`} />
            <circle cx="5" cy="23.8" r="1.1" fill="#ffffff" opacity="0.85" />
          </g>
          <g transform="translate(28 24)">
            <g className={styles.gear}>
              {teeth.map((angle) => (
                <rect key={angle} x="-2.8" y="-17" width="5.6" height="7" rx="1.3" fill={BLUE} transform={`rotate(${angle})`} />
              ))}
              <circle r="12" fill={`url(#${id}-b)`} />
            </g>
            <circle r="7.6" fill="#ffffff" />
            <g stroke={NAVY} strokeWidth="1.5">
              <ellipse cx="0" cy="-3.2" rx="4" ry="1.6" />
              <path d="M-4 -3.2 V3.2 a4 1.6 0 0 0 8 0 V-3.2" />
              <path d="M-4 0 a4 1.6 0 0 0 8 0" />
            </g>
          </g>
        </>
      )}
    </Frame>
  );
}

/** Transform: one source page fans into typed outputs (schema branches). */
export function TransformIcon(props: IconProps) {
  return (
    <Frame {...props}>
      {(id) => (
        <>
          <g className={styles.source}>
            <Page x={6} y={10} w={16} h={24} id={id} />
            <g fill={NAVY} opacity="0.6">
              <rect x="9" y="16" width="8" height="1.5" rx="0.7" />
              <rect x="9" y="20" width="10" height="1.5" rx="0.7" />
              <rect x="9" y="24" width="7" height="1.5" rx="0.7" />
            </g>
          </g>
          <g className={styles.branch} stroke={SKY} strokeWidth="1.4" strokeLinecap="round" fill="none">
            <path d="M22 22 H26" />
            <path d="M26 22 L32 12" />
            <path d="M26 22 L33 22" />
            <path d="M26 22 L32 34" />
          </g>
          <g className={styles.outA}>
            <rect x="32" y="7" width="12" height="9" rx="2" fill="#eef5ff" stroke={BLUE} strokeWidth="1.3" />
            <rect x="34.5" y="9.5" width="7" height="1.4" rx="0.6" fill={SKY} />
            <rect x="34.5" y="12.2" width="5" height="1.4" rx="0.6" fill={NAVY} opacity="0.45" />
          </g>
          <g className={styles.outB}>
            <rect x="33" y="18" width="12" height="9" rx="2" fill="#fff1e3" stroke={ORANGE} strokeWidth="1.3" />
            <rect x="35.5" y="20.5" width="7" height="1.4" rx="0.6" fill={ORANGE} />
            <rect x="35.5" y="23.2" width="5" height="1.4" rx="0.6" fill={NAVY} opacity="0.45" />
          </g>
          <g className={styles.outC}>
            <rect x="32" y="29" width="12" height="9" rx="2" fill="#e8f8ef" stroke="#1f8a4c" strokeWidth="1.3" />
            <rect x="34.5" y="31.5" width="7" height="1.4" rx="0.6" fill="#1f8a4c" />
            <rect x="34.5" y="34.2" width="5" height="1.4" rx="0.6" fill={NAVY} opacity="0.45" />
          </g>
        </>
      )}
    </Frame>
  );
}

/** Analyze: bars rise as a page is scored / compared. */
export function AnalyzeIcon(props: IconProps) {
  return (
    <Frame {...props}>
      {(id) => (
        <>
          <Page x={5} y={7} w={18} h={28} id={id} />
          <g fill={NAVY} opacity="0.5">
            <rect x="8.5" y="13" width="9" height="1.5" rx="0.7" />
            <rect x="8.5" y="17" width="11" height="1.5" rx="0.7" />
            <rect x="8.5" y="21" width="8" height="1.5" rx="0.7" />
          </g>
          <rect x="26" y="10" width="18" height="28" rx="3" fill={`url(#${id}-b)`} opacity="0.12" stroke={BLUE} strokeWidth="1.3" />
          <g className={styles.bars} transform="translate(29 34)">
            <rect className={styles.bar1} x="0" y="-8" width="3.2" height="8" rx="1" fill={SKY} />
            <rect className={styles.bar2} x="5" y="-14" width="3.2" height="14" rx="1" fill={BLUE} />
            <rect className={styles.bar3} x="10" y="-11" width="3.2" height="11" rx="1" fill={`url(#${id}-o)`} />
          </g>
          <circle className={styles.pulse} cx="40" cy="14" r="3.2" fill={ORANGE} opacity="0.9" />
        </>
      )}
    </Frame>
  );
}

/** Report: structured checklist / export sheet with a confirming check. */
export function ReportIcon(props: IconProps) {
  return (
    <Frame {...props}>
      {(id) => (
        <>
          <Page x={9} y={5} w={24} h={34} id={id} />
          <g className={styles.rows}>
            {[0, 1, 2, 3].map((row) => (
              <g key={row} transform={`translate(13 ${12 + row * 5.5})`}>
                <rect width="3.2" height="3.2" rx="0.8" fill={row < 3 ? "#1f8a4c" : SKY} opacity={row < 3 ? 1 : 0.55} />
                {row < 3 && (
                  <path
                    d="M0.7 1.6 l0.9 0.9 l1.6 -1.7"
                    stroke="#ffffff"
                    strokeWidth="0.9"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}
                <rect x="5" y="0.7" width={row === 1 ? 12 : 10} height="1.6" rx="0.7" fill={NAVY} opacity="0.55" />
              </g>
            ))}
          </g>
          <g className={styles.badge}>
            <circle cx="36" cy="36" r="8" fill={`url(#${id}-b)`} />
            <path d="M32.6 36.2 l2.4 2.4 l4.6 -4.8" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        </>
      )}
    </Frame>
  );
}

/** Verify: a read page earns its check. */
export function VerifyIcon(props: IconProps) {
  return (
    <Frame {...props}>
      {(id) => (
        <>
          <Page x={8} y={5} w={24} h={34} id={id} />
          <g fill={NAVY}>
            <rect x="12" y="12" width="12" height="2" rx="1" />
            <rect x="12" y="17.5" width="15" height="2" rx="1" />
            <rect x="12" y="23" width="10" height="2" rx="1" />
          </g>
          <g className={styles.badge}>
            <path d="M34 22 l9 3.4 v6.2 c0 5.4 -3.8 9.4 -9 11.4 c-5.2 -2 -9 -6 -9 -11.4 v-6.2 Z" fill={`url(#${id}-b)`} />
            <path d="M29.6 32.2 l3.2 3.2 l6 -6.4" stroke="#ffffff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        </>
      )}
    </Frame>
  );
}

/** Split: one package eases apart into its documents along an orange cut. */
export function SplitIcon(props: IconProps) {
  return (
    <Frame {...props}>
      {(id) => (
        <>
          <g className={styles.left}>
            <Page x={5} y={9} w={18} h={28} id={id} />
            <g fill={NAVY}>
              <rect x="8.5" y="16" width="9" height="1.8" rx="0.9" />
              <rect x="8.5" y="21" width="10" height="1.8" rx="0.9" />
              <rect x="8.5" y="26" width="7" height="1.8" rx="0.9" />
            </g>
          </g>
          <g className={styles.right}>
            <Page x={25} y={9} w={18} h={28} id={id} />
            <g fill={BLUE}>
              <rect x="28.5" y="16" width="9" height="1.8" rx="0.9" />
              <rect x="28.5" y="21" width="10" height="1.8" rx="0.9" />
              <rect x="28.5" y="26" width="7" height="1.8" rx="0.9" />
            </g>
          </g>
          <path d="M24 4 V44" stroke="#f7931e" strokeWidth="1.6" strokeDasharray="2.6 2.6" strokeLinecap="round" />
        </>
      )}
    </Frame>
  );
}
