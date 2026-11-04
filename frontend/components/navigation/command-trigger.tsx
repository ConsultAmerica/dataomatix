"use client";

import { Search } from "lucide-react";

import { useShortcutLabel } from "@/components/navigation/client-env";

/** The header's way into the command palette: "Search or jump to…  ⌘K".
 * `compact` keeps only the icon (phones, tight headers). */
export default function CommandTrigger({
  onOpen,
  compact = false,
  kbdClassName = "hidden sm:inline",
  labelClassName = "hidden xl:inline",
}: {
  onOpen: () => void;
  compact?: boolean;
  /** When the shortcut badge shows (it is always in the accessible name). */
  kbdClassName?: string;
  /** When "Search or jump to…" shows beside the icon. */
  labelClassName?: string;
}) {
  const shortcut = useShortcutLabel();
  if (compact) {
    return (
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Search or jump to (${shortcut})`}
        aria-keyshortcuts="Control+K Meta+K"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-text-secondary transition-colors hover:bg-surface-soft hover:text-foreground"
      >
        <Search className="h-4 w-4" strokeWidth={1.75} />
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Search or jump to (${shortcut})`}
      aria-keyshortcuts="Control+K Meta+K"
      className="group inline-flex h-9 shrink-0 items-center gap-2 rounded-full border border-border bg-surface-soft pl-3 pr-1.5 text-[13px] text-text-secondary transition-colors hover:border-primary/30 hover:bg-surface hover:text-foreground"
    >
      <Search className="h-4 w-4 shrink-0" strokeWidth={1.75} />
      <span className={`whitespace-nowrap ${labelClassName}`}>Search or jump to…</span>
      <kbd className={`rounded-md border border-border bg-surface px-1.5 py-0.5 font-sans text-[10px] font-medium text-text-secondary ${kbdClassName}`}>
        {shortcut}
      </kbd>
    </button>
  );
}
