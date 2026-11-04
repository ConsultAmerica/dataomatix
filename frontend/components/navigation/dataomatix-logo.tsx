/**
 * The DataOMatix lockup: the icon, a divider and the wordmark, cut from the
 * brand artwork (public/brand). Each has a light and a dark version; CSS shows
 * the one that reads on the current chrome (globals.css, .da-logo-*). The
 * pieces stay separate so a narrow bar can drop the icon and keep the name.
 */
const MARK = { light: "/brand/dataomatix-mark.png", dark: "/brand/dataomatix-mark-on-dark.png", ratio: 406 / 214 };
const WORD = { light: "/brand/dataomatix-wordmark.png", dark: "/brand/dataomatix-wordmark-on-dark.png", ratio: 1050 / 214 };

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
  /** `mark` = the icon alone; `wordmark` = icon + divider + DataOMatix */
  variant?: "mark" | "wordmark";
  /** `onDark` for dark chrome; `onLight` for the light top bar and drawers */
  tone?: "onDark" | "onLight";
}) {
  const height = Math.round(size * 0.8);
  return (
    <span
      className={["da-logo-lockup", tone === "onDark" ? "da-logo-on-dark" : "da-logo-on-light", className].filter(Boolean).join(" ")}
      role="img"
      aria-label={title}
    >
      <Artwork art={MARK} height={variant === "mark" ? size : height} className="da-logo-mark" />
      {variant === "wordmark" && (
        <>
          <span className="da-logo-divider" aria-hidden="true" />
          <Artwork art={WORD} height={height} className="da-logo-word" />
        </>
      )}
    </span>
  );
}

function Artwork({ art, height, className }: { art: typeof MARK; height: number; className: string }) {
  const width = Math.round(height * art.ratio);
  return (
    <span className={className} aria-hidden="true">
      {/* eslint-disable-next-line @next/next/no-img-element -- small static brand art, sized here */}
      <img src={art.light} alt="" width={width} height={height} className="da-logo-art-light" draggable={false} />
      {/* eslint-disable-next-line @next/next/no-img-element -- small static brand art, sized here */}
      <img src={art.dark} alt="" width={width} height={height} className="da-logo-art-dark" draggable={false} />
    </span>
  );
}
