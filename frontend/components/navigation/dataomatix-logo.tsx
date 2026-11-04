import { useId } from "react";

/**
 * The DataOMatix lockup: a document stack read through scan brackets, fed
 * (orange) into a processing gear that holds the data, out to a structured
 * table — then the wordmark (navy "Data", orange "O", blue "Matix") over
 * "Document Intelligence". Drawn as SVG and type so it stays sharp at every
 * size and reads on light and dark chrome.
 */
export default function DataomatixLogo({
  size = 36,
  className,
  title = "DataOMatix",
  variant = "mark",
  tone = "onDark",
}: {
  size?: number;
  className?: string;
  title?: string;
  /** `mark` = the icon alone; `wordmark` = icon + DataOMatix + tagline */
  variant?: "mark" | "wordmark";
  /** `onDark` for dark chrome; `onLight` for the light top bar and drawers */
  tone?: "onDark" | "onLight";
}) {
  if (variant === "wordmark") {
    const onDark = tone === "onDark";
    return (
      <span
        className={["da-logo-lockup", onDark ? "da-logo-on-dark" : "da-logo-on-light", className]
          .filter(Boolean)
          .join(" ")}
        role="img"
        aria-label={title}
        style={{ ["--da-logo-size" as string]: `${size}px` }}
      >
        <BrandMark height={Math.round(size * 0.9)} />
        <span className="da-logo-divider" aria-hidden="true" />
        <span className="da-logo-text" aria-hidden="true">
          <span className="da-logo-word">
            <span className="da-logo-data">Data</span>
            <span className="da-logo-o">O</span>
            <span className="da-logo-matix">
              Matix
              <svg className="da-logo-swoosh" viewBox="0 0 40 12" aria-hidden="true">
                <path d="M2 9.5 C 14 12, 26 10, 36 3" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                <path d="M31.5 2.2 L 37.6 2.4 L 35.6 8" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          </span>
          <span className="da-logo-tag">Document Intelligence</span>
        </span>
      </span>
    );
  }

  return <BrandMark height={size} className={className} title={title} />;
}

/** The icon: pages → scan → gear with the data → table. Drawn on 132 × 52
 * units and cropped to the drawing (y 2.5–48.5), so it fills its height. */
export function BrandMark({ height, className, title }: { height: number; className?: string; title?: string }) {
  const id = useId().replace(/:/g, "");
  const width = Math.round((height * 132) / 46);
  const gearTeeth = Array.from({ length: 8 }, (_, index) => index * 45);
  return (
    <svg
      viewBox="0 2.5 132 46"
      width={width}
      height={height}
      className={["da-logo-mark", className].filter(Boolean).join(" ")}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <defs>
        <linearGradient id={`${id}-blue`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2f86f0" />
          <stop offset="1" stopColor="#0d47a8" />
        </linearGradient>
        <linearGradient id={`${id}-orange`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#ffb547" />
          <stop offset="1" stopColor="#f26b0a" />
        </linearGradient>
      </defs>
      {/* Data dissolving in from the left */}
      <g fill="#2f86f0">
        <rect x="3" y="17" width="3.4" height="3.4" rx="0.6" opacity="0.55" />
        <rect x="0" y="25" width="3.4" height="3.4" rx="0.6" opacity="0.8" />
        <rect x="6" y="30" width="3.4" height="3.4" rx="0.6" />
        <rect x="2" y="37" width="3.4" height="3.4" rx="0.6" opacity="0.65" />
      </g>
      {/* The document stack */}
      <rect x="11" y="7" width="27" height="40" rx="4.5" fill="#0b3a8c" />
      <rect x="14.5" y="4.5" width="27" height="41" rx="4.5" fill={`url(#${id}-blue)`} />
      <path d="M20 9.5 H36.5 L43 16 V42 a2.5 2.5 0 0 1 -2.5 2.5 H20 a2.5 2.5 0 0 1 -2.5 -2.5 V12 a2.5 2.5 0 0 1 2.5 -2.5 Z" fill="#ffffff" />
      <path d="M36.5 9.5 L43 16 H38.5 a2 2 0 0 1 -2 -2 Z" fill={`url(#${id}-orange)`} />
      <g fill="#0b2a5b">
        <rect x="22" y="19" width="14" height="2.2" rx="1.1" />
        <rect x="22" y="24.5" width="16" height="2.2" rx="1.1" />
        <rect x="22" y="30" width="12" height="2.2" rx="1.1" />
        <rect x="22" y="35.5" width="15" height="2.2" rx="1.1" />
      </g>
      {/* Scan brackets */}
      <g fill="none" stroke="#2f86f0" strokeWidth="2" strokeLinecap="round">
        <path d="M15 13 V8 H20" />
        <path d="M45 41 V46 H40" />
        <path d="M15 41 V46 H20" />
      </g>
      {/* Into the gear */}
      <rect x="43" y="23" width="13" height="7" rx="3.5" fill={`url(#${id}-orange)`} />
      <g transform="translate(67.5 26.5) scale(1.12)">
        {gearTeeth.map((angle) => (
          <rect key={angle} x="-2.6" y="-13" width="5.2" height="6" rx="1.2" fill="#1d63d1" transform={`rotate(${angle})`} />
        ))}
        <circle r="9.5" fill={`url(#${id}-blue)`} />
        <circle r="6.2" fill="#ffffff" />
        <g fill="none" stroke="#0b2a5b" strokeWidth="1.3">
          <ellipse cx="0" cy="-2.6" rx="3.2" ry="1.3" />
          <path d="M-3.2 -2.6 V2.6 a3.2 1.3 0 0 0 6.4 0 V-2.6" />
          <path d="M-3.2 0 a3.2 1.3 0 0 0 6.4 0" />
        </g>
      </g>
      {/* Out to the table */}
      <g fill="#2f86f0">
        <rect x="84" y="25" width="5.5" height="3.2" rx="1.6" />
        <path d="M88.5 21.5 L94.5 26.6 L88.5 31.7 Z" />
      </g>
      <rect x="97" y="13" width="33" height="27" rx="4.5" fill="#ffffff" stroke="#0b3a8c" strokeWidth="2.6" />
      <rect x="97" y="13" width="33" height="6" rx="3" fill="#0b3a8c" />
      <g>
        {[0, 1, 2].map((row) =>
          [0, 1, 2].map((col) => {
            const orange = (row === 1 && col > 0) || (row === 2 && col === 1);
            return (
              <rect
                key={`${row}-${col}`}
                x={101 + col * 9}
                y={22 + row * 5.6}
                width="7.4"
                height="4"
                rx="1"
                fill={orange ? `url(#${id}-orange)` : "#2f86f0"}
              />
            );
          }),
        )}
      </g>
    </svg>
  );
}
