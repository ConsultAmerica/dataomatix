"use client";

import { memo, useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { Inbox, UserRound } from "lucide-react";

import { AnalyzeIcon, ExtractIcon, ProcessIcon, ReportIcon, TransformIcon } from "@/components/brand/capability-icons";

import styles from "./pipeline-scene.module.css";

/**
 * "How it works" scene: an isometric workbench where one federal award moves
 * through the agents. Documents slide into the DataoMatix engine, a packet is
 * classified, the Extract agent scans the source page field by field (each
 * value boxed where it was read and lifted onto a card), Verify routes the
 * one doubtful value to a person, and the clean set lands as an Oracle export.
 *
 * One rAF clock drives the dynamic layer so the whole story stays in sync; the
 * static layer is memoised. Reduced-motion users (and the server render) get
 * the finished scene. The clock pauses while the scene is off screen.
 */

// ---------------------------------------------------------------- projection
const S = 30; // px per iso unit (vertical)
const CW = S * 0.8660254;
const CH = S * 0.5;
const OX = 560;
const OY = 250;
const VB_W = 1440;
const VB_H = 590;

type Pt = [number, number];
type P3 = [number, number, number];

const P = (x: number, y: number, z = 0): Pt => [OX + (x - y) * CW, OY + (x + y) * CH - z * S];
const pts = (...p: Pt[]) => p.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(" ");
const n = (v: number) => v.toFixed(2);
// Plane transforms. Local units are px (S px = 1 iso unit).
const topM = (x: number, y: number, z: number) => {
  const [e, f] = P(x, y, z);
  return `matrix(0.8660254,0.5,-0.8660254,0.5,${n(e)},${n(f)})`;
};
const frontM = (x: number, y: number, z: number) => {
  const [e, f] = P(x, y, z);
  return `matrix(0.8660254,0.5,0,1,${n(e)},${n(f)})`;
};

const clamp01 = (k: number) => Math.max(0, Math.min(1, k));
const prog = (t: number, a: number, b: number) => clamp01((t - a) / (b - a));
const easeIO = (k: number) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

// ---------------------------------------------------------------- palette
const INK = "#0b1530";
const BLUE = "#2152e8";
const ORANGE = "#ec6a1f";
const PAPER = "#fdfcf9";
const EDGE = "rgba(11,21,48,0.55)";

// ---------------------------------------------------------------- layout
// The five product stages, in the same order (and with the same brand icons)
// as the capability cards further down the page.
const EXTRACT = { x: 5.6, y: -3.4, w: 2.4, d: 2.4, h: 2.2 };
const PROCESS = { x: 10.4, y: -3.6, w: 2.4, d: 2.4, h: 2.2 };
const TRANSFORM = { x: 10.4, y: 1.5, w: 2.4, d: 2.4, h: 2.2 };
const ANALYZE = { x: 14.8, y: -1.8, w: 2.4, d: 2.4, h: 2.2 };
const REPORT = { x: 20.8, y: -6.2, w: 2.4, d: 2.4, h: 2.2 };
const DESK = { x: 15, y: 3, w: 2, d: 2, h: 0.3 };
const PAGE = { x: 12.5, y: -9.5, w: 5, h: 8.5 }; // standing sheet, local 150 x 255 px
const CARD = { x: 19.6, y: -8.3, w: 4 }; // floating field cards, local 120 x 34 px

const pagePt = (u: number, v: number): Pt => P(PAGE.x + u / S, PAGE.y, PAGE.h - v / S);
const cardTop = (r: number) => 8.2 - r * 1.35;
const cardPt = (r: number, u: number, v: number): Pt => P(CARD.x + u / S, CARD.y, cardTop(r) - v / S);

type Row = { label: string; value: string; card: string; w: number; ly: number; vy: number; conf: number; review?: boolean };
const ROWS: Row[] = [
  { label: "1. Contract no.", value: "W91ZZZ26C0042", card: "W91ZZZ26C0042", w: 80, ly: 40, vy: 53, conf: 98 },
  { label: "2. Award date", value: "08/19/2026", card: "Aug 19, 2026", w: 54, ly: 72, vy: 85, conf: 96 },
  { label: "17a. Contractor", value: "Northwind Analytics LLC", card: "Northwind Analytics", w: 116, ly: 104, vy: 117, conf: 91 },
  { label: "31. Total award", value: "$1,250,000.00", card: "$1,250,000.00", w: 84, ly: 140, vy: 154, conf: 97 },
  { label: "9. Issued by", value: "Army Contracting Cmd.", card: "2 candidates", w: 108, ly: 178, vy: 191, conf: 50, review: true },
];
const CARD_LABELS = ["Contract no.", "Award date", "Contractor", "Total award", "Issued by"];

// ---------------------------------------------------------------- timeline
const HUB = { x: 3, y: 3, w: 4, d: 4 }; // DataoMatix hub, where the documents go first
const T = 14;
const FINAL = 13.0;
const ROW_AT = (r: number) => 3.9 + r * 0.7;
type StepIcon = (p: { size?: number; animated?: boolean }) => ReactNode;
export const STEPS: { key: string; n: string; title: string; body: string; at: number; icon?: StepIcon; lucide?: typeof Inbox }[] = [
  { key: "ingest", n: "00", title: "Ingest", body: "Awards, solicitations and mods arrive as PDFs or scans.", at: 0, lucide: Inbox },
  { key: "extract", n: "01", title: "Extract", body: "Every field read and boxed where it is printed.", at: 2.8, icon: ExtractIcon },
  { key: "process", n: "02", title: "Process", body: "Typed as an SF 1449 award; schema and staging built.", at: 7.7, icon: ProcessIcon },
  { key: "transform", n: "03", title: "Transform", body: "Fanned into sections, tables and mapped fields.", at: 8.9, icon: TransformIcon },
  { key: "analyze", n: "04", title: "Analyze", body: "Scored against the page; doubtful values flagged.", at: 9.8, icon: AnalyzeIcon },
  { key: "review", n: "05", title: "Review", body: "A contract specialist settles the flagged value.", at: 10.5, lucide: UserRound },
  { key: "report", n: "06", title: "Report", body: "Verified, sourced rows your ops team can trust.", at: 11.2, icon: ReportIcon },
];
const stepIndex = (t: number) => {
  let i = 0;
  STEPS.forEach((s, k) => {
    if (t >= s.at) i = k;
  });
  return i;
};

// Floor paths (iso points) the packets travel.
const PATHS = {
  intake: [
    [2.4, 8.6, 0],
    [5, 8.6, 0],
    [5, 5, 0],
  ] as P3[],
  toExtract: [
    [5, 5, 0],
    [5, -2.2, 0],
    [6.8, -2.2, 0],
  ] as P3[],
  toProcess: [
    [6.8, -2.3, 0],
    [11.6, -2.3, 0],
  ] as P3[],
  toTransform: [
    [11.6, -2.3, 0],
    [11.6, 2.7, 0],
  ] as P3[],
  toAnalyze: [
    [11.6, 2.7, 0],
    [13.6, 2.7, 0],
    [13.6, -0.6, 0],
    [16, -0.6, 0],
  ] as P3[],
  toReviewer: [
    [16, -0.6, 0],
    [16, 4, 0],
  ] as P3[],
  toReport: [
    [16, -0.6, 0],
    [16, -5, 0],
    [22, -5, 0],
  ] as P3[],
};

function along(path: P3[], k: number): P3 {
  const seg: number[] = [];
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    const [a, b] = [path[i - 1], path[i]];
    const l = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    seg.push(l);
    total += l;
  }
  let d = clamp01(k) * total;
  for (let i = 1; i < path.length; i++) {
    if (d <= seg[i - 1] || i === path.length - 1) {
      const f = seg[i - 1] ? Math.min(1, d / seg[i - 1]) : 0;
      const [a, b] = [path[i - 1], path[i]];
      return [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
    }
    d -= seg[i - 1];
  }
  return path[path.length - 1];
}
const pathD = (path: P3[]) => "M" + path.map((p) => P(p[0], p[1], p[2]).map((v) => v.toFixed(1)).join(",")).join(" L");

// ---------------------------------------------------------------- clock
function useSceneClock(rootRef: React.RefObject<HTMLElement | null>) {
  const [t, setT] = useState(FINAL);
  const acc = useRef(0);
  const visible = useRef(false);
  const reduced = useRef(false);

  useEffect(() => {
    reduced.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced.current) return;
    const el = rootRef.current;
    const io = new IntersectionObserver(([e]) => (visible.current = e.isIntersecting), { threshold: 0.15 });
    if (el) io.observe(el);
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (visible.current) {
        acc.current = (acc.current + dt) % T;
        setT(acc.current);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
    };
  }, [rootRef]);

  const jump = useCallback((to: number) => {
    if (reduced.current) return;
    acc.current = to;
    setT(to);
  }, []);
  return { t, jump };
}

// ---------------------------------------------------------------- component
export default function PipelineScene() {
  const rootRef = useRef<HTMLElement | null>(null);
  const { t, jump } = useSceneClock(rootRef);
  const active = stepIndex(t);

  return (
    <section ref={rootRef} className={styles.band} aria-labelledby="pipeline-title">
      <div className={styles.head}>
        <p className={styles.eyebrow}>How it works</p>
        <h2 id="pipeline-title" className={styles.title}>
          A stack of PDFs in. <em>Oracle&#8209;ready data out.</em>
        </h2>
        <p className={styles.lede}>
          Follow one award through the agents: typed, read field by field, every value boxed on its page, and the one
          value it can&rsquo;t trust handed to a person instead of guessed.
        </p>
      </div>

      <div className={styles.stageWrap}>
        <svg
          className={styles.svg}
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          role="img"
          aria-label="Illustration: documents flow into the DataoMatix engine, through Classify, Extract and Verify agents, to a reviewer and an Oracle export."
        >
          <StaticLayer />
          <DynamicLayer t={t} />
        </svg>
      </div>

      <ol className={styles.steps}>
        {STEPS.map((s, i) => (
          <li key={s.key}>
            <button
              type="button"
              className={styles.step}
              data-active={i === active ? "" : undefined}
              data-done={i < active ? "" : undefined}
              onClick={() => jump(s.at + 0.01)}
              aria-current={i === active ? "step" : undefined}
            >
              <span className={styles.stepTop}>
                <span className={styles.stepIcon} aria-hidden="true">
                  {s.icon ? <s.icon size={30} animated={i === active} /> : s.lucide ? <s.lucide className="h-4 w-4" strokeWidth={1.8} /> : null}
                </span>
                <span className={styles.stepN}>{s.n}</span>
              </span>
              <span className={styles.stepTitle}>{s.title}</span>
              <span className={styles.stepBody}>{s.body}</span>
              <span className={styles.stepBar} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ---------------------------------------------------------------- primitives
type CubeProps = {
  x: number;
  y: number;
  w: number;
  d: number;
  h: number;
  top: string;
  left: string;
  right: string;
  shadow?: boolean;
  z?: number;
  children?: ReactNode;
};
function Cube({ x, y, w, d, h, top, left, right, shadow = true, z = 0, children }: CubeProps) {
  return (
    <g>
      {shadow && (
        <polygon
          points={pts(P(x + 0.25, y + 0.25, z), P(x + w + 0.55, y + 0.25, z), P(x + w + 0.55, y + d + 0.55, z), P(x + 0.25, y + d + 0.55, z))}
          fill={INK}
          opacity={0.14}
          filter="url(#dx-soft)"
        />
      )}
      <polygon points={pts(P(x, y + d, z), P(x + w, y + d, z), P(x + w, y + d, z + h), P(x, y + d, z + h))} fill={left} stroke={EDGE} strokeWidth={1} strokeLinejoin="round" />
      <polygon points={pts(P(x + w, y, z), P(x + w, y + d, z), P(x + w, y + d, z + h), P(x + w, y, z + h))} fill={right} stroke={EDGE} strokeWidth={1} strokeLinejoin="round" />
      <polygon points={pts(P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + d, z + h), P(x, y + d, z + h))} fill={top} stroke={EDGE} strokeWidth={1} strokeLinejoin="round" />
      {children}
    </g>
  );
}

function FlatDoc({ x, y, z = 0, w = 2.4, d = 3.1, table = false }: { x: number; y: number; z?: number; w?: number; d?: number; table?: boolean }) {
  const W = w * S;
  const D = d * S;
  return (
    <g>
      <polygon points={pts(P(x + 0.12, y + 0.12, 0), P(x + w + 0.2, y + 0.12, 0), P(x + w + 0.2, y + d + 0.2, 0), P(x + 0.12, y + d + 0.2, 0))} fill={INK} opacity={0.08} />
      <g transform={topM(x, y, z + 0.02)}>
        <rect width={W} height={D} fill={PAPER} stroke={EDGE} strokeWidth={0.8} vectorEffect="non-scaling-stroke" />
        <rect x={8} y={8} width={W * 0.45} height={5} rx={1} fill={INK} opacity={0.55} />
        {table ? (
          <g stroke={INK} strokeOpacity={0.25} strokeWidth={0.8} fill="none" vectorEffect="non-scaling-stroke">
            <rect x={8} y={22} width={W - 16} height={D - 34} />
            {[0.25, 0.5, 0.75].map((f) => (
              <line key={f} x1={8} x2={W - 8} y1={22 + (D - 34) * f} y2={22 + (D - 34) * f} />
            ))}
            <line x1={W * 0.45} x2={W * 0.45} y1={22} y2={D - 12} />
          </g>
        ) : (
          Array.from({ length: Math.floor((D - 28) / 9) }, (_, i) => (
            <rect key={i} x={8} y={22 + i * 9} width={(W - 16) * (i % 3 === 2 ? 0.6 : 0.92)} height={3} rx={1.5} fill={INK} opacity={0.14} />
          ))
        )}
      </g>
    </g>
  );
}

// ---------------------------------------------------------------- static layer
const StaticLayer = memo(function StaticLayer() {
  const gridLines: ReactNode[] = [];
  for (let k = -12; k <= 32; k += 2) {
    gridLines.push(<line key={`x${k}`} x1={P(k, -22)[0]} y1={P(k, -22)[1]} x2={P(k, 30)[0]} y2={P(k, 30)[1]} />);
  }
  for (let k = -22; k <= 30; k += 2) {
    gridLines.push(<line key={`y${k}`} x1={P(-12, k)[0]} y1={P(-12, k)[1]} x2={P(32, k)[0]} y2={P(32, k)[1]} />);
  }

  return (
    <g>
      <defs>
        <filter id="dx-soft" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" />
        </filter>
        <filter id="dx-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <clipPath id="dx-floor-clip">
          <rect x={22} y={176} width={VB_W - 44} height={VB_H - 182} rx={22} />
        </clipPath>
        <linearGradient id="dx-face-r" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#dcdde3" />
        </linearGradient>
        <linearGradient id="dx-face-l" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#f4f3ef" />
          <stop offset="1" stopColor="#e4e2db" />
        </linearGradient>
        <linearGradient id="dx-blue-face" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#3a68f0" />
          <stop offset="1" stopColor={BLUE} />
        </linearGradient>
        <linearGradient id="dx-orange-face" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#f2843e" />
          <stop offset="1" stopColor={ORANGE} />
        </linearGradient>
        <linearGradient id="dx-sky-face" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#4b9af5" />
          <stop offset="1" stopColor="#1d63d1" />
        </linearGradient>
        <linearGradient id="dx-ink-face" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#1d2a52" />
          <stop offset="1" stopColor={INK} />
        </linearGradient>
        <radialGradient id="dx-mouth" cx="0.5" cy="0.6" r="0.7">
          <stop offset="0" stopColor={ORANGE} stopOpacity="0.95" />
          <stop offset="0.55" stopColor="#7a2d0a" stopOpacity="0.9" />
          <stop offset="1" stopColor={INK} />
        </radialGradient>
        <linearGradient id="dx-intake" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor={ORANGE} stopOpacity="0" />
          <stop offset="1" stopColor={ORANGE} stopOpacity="0.28" />
        </linearGradient>
        <pattern id="dx-dots" width="5" height="5" patternUnits="userSpaceOnUse">
          <circle cx="1.5" cy="1.5" r="0.9" fill={INK} opacity="0.55" />
        </pattern>
      </defs>

      {/* floor */}
      <rect className={styles.floor} x={22} y={176} width={VB_W - 44} height={VB_H - 182} rx={22} />
      <g clipPath="url(#dx-floor-clip)" className={styles.grid}>
        {gridLines}
      </g>

      {/* floor connectors */}
      {Object.entries(PATHS).map(([k, p]) => (
        <g key={k}>
          <path d={pathD(p)} className={styles.trackBase} />
          <path d={pathD(p)} className={styles.track} />
        </g>
      ))}

      {/* inbox: documents on the floor */}
      <FlatDoc x={-3} y={12.4} />
      <FlatDoc x={-0.8} y={13.4} z={0.04} table />
      <FlatDoc x={-1.6} y={9.2} />
      <FlatDoc x={0.4} y={11.2} z={0.05} table />
      <FlatDoc x={1.6} y={8.1} z={0.02} />
      <text className={styles.floorTag} transform={topM(-3, 16.4, 0)} x={2} y={-4}>
        INBOX · 14 PDF · 3 SCANS
      </text>

      {/* DataoMatix hub: the brand mark floating over its pad */}
      <Hub />

      {/* agents: the five product stages */}
      <AgentCube box={EXTRACT} face="url(#dx-orange-face)" delay={0} title="Extract" n="01" Icon={ExtractIcon} />
      <AgentCube box={PROCESS} face="url(#dx-blue-face)" delay={0.6} title="Process" n="02" Icon={ProcessIcon} />
      <AgentCube box={TRANSFORM} face="url(#dx-ink-face)" delay={1.2} title="Transform" n="03" Icon={TransformIcon} />
      <AgentCube box={ANALYZE} face="url(#dx-sky-face)" delay={1.8} title="Analyze" n="04" Icon={AnalyzeIcon} />

      {/* reviewer desk */}
      <Cube x={DESK.x} y={DESK.y} w={DESK.w} d={DESK.d} h={DESK.h} top="#f6f5f1" left="#e6e4dd" right="#eeede8" />

      {/* standing source page */}
      <polygon points={pts(P(PAGE.x - 0.2, PAGE.y, 0), P(PAGE.x + PAGE.w + 0.2, PAGE.y, 0), P(PAGE.x + PAGE.w + 0.2, PAGE.y + 0.55, 0), P(PAGE.x - 0.2, PAGE.y + 0.55, 0))} className={styles.stand} />
      <polygon points={pts(P(PAGE.x + 0.3, PAGE.y + 0.5, 0), P(PAGE.x + PAGE.w + 0.9, PAGE.y + 0.5, 0), P(PAGE.x + PAGE.w + 1.4, PAGE.y + 2.2, 0), P(PAGE.x + 0.8, PAGE.y + 2.2, 0))} fill={INK} opacity={0.1} filter="url(#dx-soft)" />
      <g transform={frontM(PAGE.x, PAGE.y, PAGE.h)}>
        <rect width={PAGE.w * S} height={PAGE.h * S} fill={PAPER} stroke={BLUE} strokeOpacity={0.55} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
        <text x={10} y={16} className={styles.pageHead}>
          AWARD / CONTRACT
        </text>
        <text x={140} y={16} textAnchor="end" className={styles.pageMeta}>
          SF 1449 · p.1
        </text>
        <line x1={10} x2={140} y1={23} y2={23} stroke={INK} strokeOpacity={0.3} strokeWidth={0.8} vectorEffect="non-scaling-stroke" />
        {ROWS.map((r) => (
          <g key={r.label}>
            <text x={10} y={r.ly} className={styles.pageLabel}>
              {r.label}
            </text>
            <text x={10} y={r.vy} textLength={r.w - 2} lengthAdjust="spacingAndGlyphs" className={r.label.startsWith("31") ? styles.pageValueStrong : styles.pageValue}>
              {r.value}
            </text>
          </g>
        ))}
        {[204, 214, 224, 234, 244].map((y, i) => (
          <rect key={y} x={10} y={y} width={i % 2 ? 96 : 128} height={3} rx={1.5} fill={INK} opacity={0.12} />
        ))}
      </g>

      {/* Report sits in front of the page */}
      <AgentCube box={REPORT} face="url(#dx-ink-face)" delay={2.4} title="Report" n="06" Icon={ReportIcon} />

      {/* reviewer figure */}
      <Reviewer />
    </g>
  );
});

// Floating icon tile for a stage: no block, just the brand icon hovering
// over a pad on the floor, with its number and name underneath.
const TILE = 72;
const LIFT = 92; // px the tile floats above its floor spot
const stageCenter = (b: { x: number; y: number; w: number; d: number }) => P(b.x + b.w / 2, b.y + b.d / 2, 0);
const tileRect = (b: { x: number; y: number; w: number; d: number }) => {
  const [cx, cy] = stageCenter(b);
  return { x: cx - TILE / 2, y: cy - LIFT, cx, cy };
};

function AgentCube({
  box,
  title,
  n: num,
  Icon,
  delay = 0,
}: {
  box: { x: number; y: number; w: number; d: number; h: number };
  face?: string;
  title: string;
  n: string;
  Icon: (p: { size?: number; animated?: boolean }) => ReactNode;
  delay?: number;
}) {
  const { x, y, w, d } = box;
  const r = tileRect(box);
  return (
    <g>
      {/* pad on the floor */}
      <polygon
        points={pts(P(x + 0.2, y + 0.2, 0), P(x + w - 0.2, y + 0.2, 0), P(x + w - 0.2, y + d - 0.2, 0), P(x + 0.2, y + d - 0.2, 0))}
        className={styles.pad}
      />
      <ellipse cx={r.cx} cy={r.cy} rx={30} ry={12} className={styles.padShadow} style={{ animationDelay: `${delay}s` }} />
      <line x1={r.cx} y1={r.cy} x2={r.cx} y2={r.y + TILE} className={styles.stem} />
      {/* floating tile */}
      <g className={styles.float} style={{ animationDelay: `${delay}s` }}>
        <g transform={`translate(${r.x} ${r.y})`} className={styles.iconLift}>
          <Icon size={TILE} animated />
        </g>
        <text x={r.cx} y={r.y - 18} textAnchor="middle" className={styles.tileNum}>
          {num}
        </text>
        <text x={r.cx} y={r.y - 5} textAnchor="middle" className={styles.tileName}>
          {title}
        </text>
      </g>
    </g>
  );
}

function Hub() {
  const { x, y, w, d } = HUB;
  const [cx, cy] = P(x + w / 2, y + d / 2, 0);
  return (
    <g>
      <polygon points={pts(P(x, y, 0), P(x + w, y, 0), P(x + w, y + d, 0), P(x, y + d, 0))} className={styles.hubPad} />
      <polygon points={pts(P(x + 0.6, y + 0.6, 0), P(x + w - 0.6, y + 0.6, 0), P(x + w - 0.6, y + d - 0.6, 0), P(x + 0.6, y + d - 0.6, 0))} className={styles.hubRing} />
      <ellipse cx={cx} cy={cy} rx={56} ry={22} className={styles.padShadow} />
      <line x1={cx} y1={cy} x2={cx} y2={cy - 82} className={styles.stem} />
      <g className={styles.float}>
        <image href="/brand/dataomatix-wordmark.png" x={cx - 120} y={cy - 138} width={240} height={52} className={styles.hubWordLight} />
        <image href="/brand/dataomatix-wordmark-on-dark.png" x={cx - 120} y={cy - 138} width={240} height={52} className={styles.hubWordDark} />
      </g>
    </g>
  );
}

function Reviewer() {
  const [bx, by] = P(DESK.x + 1, DESK.y + 1, DESK.h);
  return (
    <g>
      <ellipse cx={bx} cy={by + 2} rx={16} ry={6} fill={INK} opacity={0.12} />
      <path className={styles.person} d={`M${bx - 11} ${by} v-22 a11 11 0 0 1 22 0 v22 z`} />
      <circle className={styles.person} cx={bx} cy={by - 42} r={9} />
      <path d={`M${bx - 6} ${by - 22} l6 6 l6 -6`} fill="none" stroke="#fff" strokeOpacity={0.5} strokeWidth={1.4} />
    </g>
  );
}

// ---------------------------------------------------------------- dynamic layer
function Packet({ path, k, color = ORANGE }: { path: P3[]; k: number; color?: string }) {
  if (k <= 0 || k >= 1) return null;
  const [x, y, z] = along(path, easeIO(k));
  const [sx, sy] = P(x, y, z + 0.12);
  return (
    <g>
      <circle cx={sx} cy={sy} r={11} fill={color} opacity={0.25} filter="url(#dx-glow)" />
      <circle cx={sx} cy={sy} r={4.5} fill={color} stroke="#fff" strokeWidth={1.5} />
    </g>
  );
}

function Tag({ at, children, tone = "ink", show, dx = 0, dy = 0 }: { at: Pt; children: ReactNode; tone?: "ink" | "orange" | "blue"; show: number; dx?: number; dy?: number }) {
  if (show <= 0) return null;
  return (
    <foreignObject x={at[0] - 110 + dx} y={at[1] - 30 + dy - (1 - show) * 8} width={220} height={30} opacity={show} style={{ overflow: "visible" }}>
      <div className={styles.tagWrap}>
        <span className={styles.tag} data-tone={tone}>
          {children}
        </span>
      </div>
    </foreignObject>
  );
}

function DynamicLayer({ t }: { t: number }) {
  const fade = t > 13.4 ? 1 - prog(t, 13.4, 14) : 1;

  // chips lifting from the inbox to the Extract stage
  const chips = ["PDF", "TIF", "PDF"].map((label, i) => {
    const a = 0.2 + i * 0.55;
    const k = prog(t, a, a + 1.9);
    if (k <= 0 || k >= 1) return null;
    const e = easeIO(k);
    const A: P3 = [-0.6 + i * 0.9, 12 - i * 0.6, 0.15];
    const C: P3 = [2.6, 8.4, 3.6];
    const B: P3 = [4.6, 4.6, 3.4];
    const q = (j: 0 | 1 | 2) => (1 - e) * (1 - e) * A[j] + 2 * (1 - e) * e * C[j] + e * e * B[j];
    const [x, y, z] = [q(0), q(1), q(2)];
    const s = 0.8;
    const op = k > 0.9 ? 1 - (k - 0.9) / 0.1 : Math.min(1, k * 6);
    return (
      <g key={i} opacity={op}>
        <polygon points={pts(P(x, y + s, z), P(x + s, y + s, z), P(x + s, y + s, z + 0.2), P(x, y + s, z + 0.2))} fill="#cfd8f7" stroke={EDGE} strokeWidth={0.8} />
        <polygon points={pts(P(x + s, y, z), P(x + s, y + s, z), P(x + s, y + s, z + 0.2), P(x + s, y, z + 0.2))} fill="#e7ebf8" stroke={EDGE} strokeWidth={0.8} />
        <polygon points={pts(P(x, y, z + 0.2), P(x + s, y, z + 0.2), P(x + s, y + s, z + 0.2), P(x, y + s, z + 0.2))} fill={INK} stroke={EDGE} strokeWidth={0.8} />
        <text transform={topM(x, y, z + 0.2)} x={4} y={15} className={styles.chipText}>
          {label}
        </text>
      </g>
    );
  });


  // extraction scan
  const scanOn = t >= 3.7 && t <= 7.6;
  const kf = clamp01((t - 3.75) / 0.7);
  const ri = Math.min(4, Math.floor(kf));
  const fr = easeIO(clamp01((kf - ri) * 1.6));
  const yA = ROWS[ri].vy;
  const yB = ROWS[Math.min(4, ri + 1)].vy;
  const scanY = (ri >= 4 ? yA : lerp(yA, yB, kf >= 4 ? 0 : fr)) - 16;
  const scanCorners: Pt[] = [pagePt(6, scanY), pagePt(144, scanY), pagePt(144, scanY + 22), pagePt(6, scanY + 22)];
  const er = tileRect(EXTRACT);
  const exTop: Pt[] = [
    [er.x + 10, er.y + 10],
    [er.x + TILE - 10, er.y + 10],
    [er.x + TILE - 10, er.y + TILE - 10],
    [er.x + 10, er.y + TILE - 10],
  ];
  const beamOp = prog(t, 3.6, 3.9) * (1 - prog(t, 7.3, 7.6));

  const processTag = prog(t, 8.3, 8.6);
  const reviewOn = prog(t, 11.0, 11.3);
  const exportOn = prog(t, 11.8, 12.1);

  return (
    <g opacity={fade}>
      {(() => {
        const hot = prog(t, 0.6, 1.4) * (1 - prog(t, 3.0, 3.8));
        const [hx, hy] = P(HUB.x + HUB.w / 2, HUB.y + HUB.d / 2, 0);
        return hot > 0 ? <ellipse cx={hx} cy={hy} rx={90} ry={40} fill={ORANGE} opacity={0.22 * hot} filter="url(#dx-glow)" /> : null;
      })()}
      {chips}
      <Packet path={PATHS.toExtract} k={prog(t, 2.8, 3.6)} color={BLUE} />

      {/* packets on the floor tracks */}
      <Packet path={PATHS.toProcess} k={prog(t, 7.7, 8.4)} color={BLUE} />
      <Packet path={PATHS.toTransform} k={prog(t, 8.9, 9.6)} color={BLUE} />
      <Packet path={PATHS.toAnalyze} k={prog(t, 9.8, 10.4)} color={BLUE} />
      <Packet path={PATHS.toReviewer} k={prog(t, 10.5, 11.1)} />
      <Packet path={PATHS.toReport} k={prog(t, 11.2, 11.8)} color={BLUE} />

      {/* stage activity halos */}
      <Halo box={EXTRACT} on={prog(t, 3.4, 3.7) * (1 - prog(t, 7.4, 7.7))} color={ORANGE} />
      <Halo box={PROCESS} on={prog(t, 8.2, 8.4) * (1 - prog(t, 8.9, 9.1))} color={BLUE} />
      <Halo box={TRANSFORM} on={prog(t, 9.4, 9.6) * (1 - prog(t, 9.9, 10.1))} color={INK} />
      <Halo box={ANALYZE} on={prog(t, 10.2, 10.4) * (1 - prog(t, 10.8, 11))} color={BLUE} />
      <Halo box={REPORT} on={prog(t, 11.6, 11.8)} color={BLUE} />

      {/* extraction beam */}
      {scanOn && beamOp > 0 && (
        <g opacity={beamOp}>
          <polygon points={pts(exTop[0], exTop[1], scanCorners[1], scanCorners[0])} fill={ORANGE} opacity={0.06} />
          <polygon points={pts(exTop[3], exTop[2], scanCorners[2], scanCorners[3])} fill={ORANGE} opacity={0.08} />
          {exTop.map((p, i) => (
            <line key={i} x1={p[0]} y1={p[1]} x2={scanCorners[i][0]} y2={scanCorners[i][1]} className={styles.beamLine} />
          ))}
          <polygon points={pts(...scanCorners)} fill={ORANGE} fillOpacity={0.1} stroke={ORANGE} strokeWidth={1.2} />
        </g>
      )}

      {/* evidence boxes on the page */}
      <g transform={frontM(PAGE.x, PAGE.y, PAGE.h)}>
        {ROWS.map((r, i) => {
          const k = prog(t, ROW_AT(i), ROW_AT(i) + 0.35);
          if (k <= 0) return null;
          const per = 2 * (r.w + 8 + 16);
          return (
            <rect
              key={r.label}
              x={6}
              y={r.vy - 11}
              width={r.w + 8}
              height={15}
              rx={2}
              fill={ORANGE}
              fillOpacity={0.1 * k}
              stroke={ORANGE}
              strokeWidth={1.4}
              strokeDasharray={r.review ? "4 3" : `${per}`}
              strokeDashoffset={r.review ? 0 : per * (1 - k)}
              opacity={r.review ? k : 1}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </g>

      {/* field cards, each tied to its box */}
      {ROWS.map((r, i) => {
        const k = prog(t, ROW_AT(i) + 0.2, ROW_AT(i) + 0.55);
        if (k <= 0) return null;
        const from = pagePt(r.w + 14, r.vy - 4);
        const to = cardPt(i, 0, 17);
        const lift = (1 - easeIO(k)) * 10;
        return (
          <g key={r.label} opacity={k}>
            <line x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1] + lift} className={styles.tether} />
            <circle cx={from[0]} cy={from[1]} r={2.2} fill={ORANGE} />
            <g transform={`translate(0 ${lift.toFixed(1)})`}>
              <g transform={frontM(CARD.x, CARD.y, cardTop(i))}>
                <rect width={CARD.w * S} height={34} rx={5} fill="#ffffff" stroke={r.review ? ORANGE : EDGE} strokeWidth={r.review ? 1.4 : 0.8} strokeDasharray={r.review ? "4 3" : undefined} vectorEffect="non-scaling-stroke" />
                <text x={8} y={12} className={styles.cardLabel}>
                  {CARD_LABELS[i]}
                </text>
                <text x={8} y={26} className={r.review ? styles.cardValueReview : styles.cardValue}>
                  {r.card}
                </text>
                <rect x={88} y={5} width={26} height={11} rx={5.5} fill={r.review ? ORANGE : INK} opacity={r.review ? 1 : 0.9} />
                <text x={101} y={13} textAnchor="middle" className={styles.cardConf}>
                  {r.review ? "?" : `${r.conf}%`}
                </text>
              </g>
            </g>
          </g>
        );
      })}

      {/* tags */}
      <Tag at={P(PROCESS.x + 1.2, PROCESS.y + 1.2, PROCESS.h + 1.7)} show={processTag} tone="blue" dx={120} dy={14}>
        SF 1449 award · schema v3
      </Tag>
      <Tag at={P(DESK.x + 1, DESK.y + 1, 0.3)} show={reviewOn} tone="orange" dx={150} dy={22}>
        Issued by · needs a person
      </Tag>
      <Tag at={P(REPORT.x + REPORT.w, REPORT.y + REPORT.d, 0)} show={exportOn} tone="ink" dx={70} dy={22}>
        Review&#8209;ready · 42 rows
      </Tag>

      {/* reviewer ring + export glow */}
      {reviewOn > 0 && (
        <ellipse cx={P(DESK.x + 1, DESK.y + 1, DESK.h)[0]} cy={P(DESK.x + 1, DESK.y + 1, DESK.h)[1] + 1} rx={30} ry={13} fill="none" stroke={ORANGE} strokeWidth={2} opacity={reviewOn} className={styles.ring} />
      )}
      {exportOn > 0 && <circle cx={tileRect(REPORT).cx} cy={tileRect(REPORT).y + TILE / 2} r={46} fill={BLUE} opacity={0.18 * exportOn} filter="url(#dx-glow)" />}
    </g>
  );
}

function Halo({ box, on, color }: { box: { x: number; y: number; w: number; d: number }; on: number; color: string }) {
  if (on <= 0) return null;
  const { x, y, w, d } = box;
  return (
    <polygon
      points={pts(P(x - 0.35, y - 0.35, 0.01), P(x + w + 0.35, y - 0.35, 0.01), P(x + w + 0.35, y + d + 0.35, 0.01), P(x - 0.35, y + d + 0.35, 0.01))}
      fill="none"
      stroke={color}
      strokeWidth={2}
      opacity={on * 0.85}
      strokeDasharray="6 5"
      className={styles.halo}
    />
  );
}
