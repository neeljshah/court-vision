// HonestState -- the shared, canonical "honest degradation" UI family.
//
// ROBUST = HONEST DEGRADATION: under any failure the SUCCESS state is an
// explicit, calm "Unavailable / Empty / Stale / Degraded" panel -- NEVER a crash,
// a blank, a spinner-forever, or a fabricated green/number. These components are
// the ONE place that look-and-feel lives so every page degrades identically.
//
// Variants:
//   * Unavailable -- the feed/endpoint could not be reached (degraded, not green).
//   * Empty       -- the feed was reached and is genuinely empty (honest "none").
//   * Stale       -- last-good data is shown but the feed is old (stale-never-green).
//   * Degraded    -- a partial/fallback mode is active (e.g. poll instead of live).
//
// NO $ field, no guessed number, no edge claim ever passes through here -- this is
// chrome around the absence of trustworthy data.
//
// ARIA semantics:
//   * Unavailable -- role="alert" (implicit aria-live="assertive"): a real failure
//     that a screen reader should announce immediately, interrupting any ongoing
//     announcement. This is the only variant that uses assertive/alert semantics.
//   * Empty / Stale / Degraded -- role="status" (implicit aria-live="polite"):
//     informational state changes that announce only when the SR is idle.
//
// State word always in the accessibility tree:
//   When a caller supplies a custom `title`, the visible label text overrides the
//   default variant word. A visually-hidden <span> with the variant word is
//   ALWAYS rendered so screen readers can announce the state regardless of the
//   custom title. Sighted output is unchanged.

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "unavailable" | "empty" | "stale" | "degraded";

const TONE: Record<Variant, { box: string; label: string; word: string }> = {
  // Unavailable -> amber (the existing p6 Unavailable tone; a real failure).
  unavailable: {
    box: "border-amber-900/40 bg-amber-950/20",
    label: "text-amber-400",
    word: "unavailable",
  },
  // Empty -> neutral slate (not an error -- there is just nothing yet).
  empty: {
    box: "border-slate-800 bg-surface-1/40",
    label: "text-muted-foreground",
    word: "nothing here yet",
  },
  // Stale -> amber (last-good shown, but explicitly NOT green/fresh).
  stale: {
    box: "border-amber-900/40 bg-amber-950/15",
    label: "text-amber-400",
    word: "stale",
  },
  // Degraded -> amber (a fallback path is active; honest, not a failure).
  degraded: {
    box: "border-amber-900/30 bg-amber-950/10",
    label: "text-amber-400",
    word: "degraded",
  },
};

// Variants that need the assertive/alert live-region semantic.
// All others remain role="status" (polite).
const ASSERTIVE_VARIANTS = new Set<Variant>(["unavailable"]);

function Frame({
  variant,
  title,
  reason,
  children,
  className,
}: {
  variant: Variant;
  title?: string;
  reason?: string | null;
  children?: ReactNode;
  className?: string;
}) {
  const t = TONE[variant];
  // Use role="alert" (assertive) only for genuine failures (Unavailable).
  // role="status" (polite) for informational states (Empty, Stale, Degraded).
  const role = ASSERTIVE_VARIANTS.has(variant) ? "alert" : "status";

  // The visible label shown to sighted users.
  const visibleLabel = title ?? t.word;

  // Whether the caller overrode the title: when they did, the visible label no
  // longer contains the state variant word, so we inject it as sr-only text so
  // screen readers still announce which state this panel represents.
  const needsSrWord = title !== undefined && title !== t.word;

  return (
    <div
      role={role}
      data-honest-state={variant}
      className={cn(
        "flex flex-col gap-1 rounded-lg border px-3 py-3 text-sm",
        t.box,
        className,
      )}
    >
      <span className={cn("font-mono text-xs uppercase tracking-wide", t.label)}>
        {visibleLabel}
        {needsSrWord ? (
          // Visually hidden -- announces the variant word to AT even when the
          // caller has supplied a custom title that replaces the default word.
          // display:none / visibility:hidden would suppress it from AT; we use
          // the standard sr-only clip-rect pattern so it IS in the a11y tree.
          <span
            aria-hidden={false}
            className="sr-only"
            data-sr-state={variant}
          >
            {" "}({t.word})
          </span>
        ) : null}
      </span>
      {reason ? <span className="text-xs text-muted-foreground">{reason}</span> : null}
      {children}
    </div>
  );
}

/** Endpoint/feed unreachable -- the canonical degraded (NOT green) state.
 *  Rendered as role="alert" (assertive live region): a real failure that
 *  screen readers announce immediately.
 */
export function Unavailable({
  reason,
  title,
  className,
}: {
  reason?: string | null;
  title?: string;
  className?: string;
}) {
  return <Frame variant="unavailable" title={title} reason={reason} className={className} />;
}

/** Feed reached but genuinely empty -- an honest "none", not an error.
 *  Rendered as role="status" (polite live region).
 */
export function Empty({
  label = "Nothing here yet",
  hint,
  className,
}: {
  label?: string;
  hint?: string;
  className?: string;
}) {
  return <Frame variant="empty" title={label} reason={hint} className={className} />;
}

/** Last-good data is old -- shown explicitly STALE so it never reads as fresh.
 *  Rendered as role="status" (polite live region).
 */
export function Stale({
  reason,
  asOf,
  className,
}: {
  reason?: string | null;
  asOf?: string | null;
  className?: string;
}) {
  const r = asOf ? `last update ${asOf}${reason ? ` -- ${reason}` : ""}` : reason;
  return <Frame variant="stale" title="stale" reason={r} className={className} />;
}

/** A fallback / partial mode is active (e.g. poll instead of live SSE).
 *  Rendered as role="status" (polite live region).
 */
export function Degraded({
  reason,
  title = "degraded",
  className,
}: {
  reason?: string | null;
  title?: string;
  className?: string;
}) {
  return <Frame variant="degraded" title={title} reason={reason} className={className} />;
}

// HonestState -- one entry point that picks a variant. Useful where a panel wants
// to switch states from a single data check without importing four components.
export function HonestState({
  variant,
  reason,
  title,
  asOf,
  className,
}: {
  variant: Variant;
  reason?: string | null;
  title?: string;
  asOf?: string | null;
  className?: string;
}) {
  if (variant === "stale") return <Stale reason={reason} asOf={asOf} className={className} />;
  if (variant === "empty") return <Empty label={title} hint={reason ?? undefined} className={className} />;
  if (variant === "degraded") return <Degraded reason={reason} title={title} className={className} />;
  return <Unavailable reason={reason} title={title} className={className} />;
}
