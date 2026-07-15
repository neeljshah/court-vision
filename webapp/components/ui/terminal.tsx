/**
 * terminal.tsx -- Direction A "Amber Console" primitives.
 *
 * Every terminal page composes from these instead of ad-hoc cards so the
 * design language (flat bordered panels, microlabel heads, as-of stamps,
 * trust pills, signed deltas) stays uniform. Tokens live in globals.css.
 */
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Flat bordered panel -- the only container terminal pages use. */
export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section className={cn("border border-border bg-card", className)}>
      {children}
    </section>
  );
}

/** Panel header: microlabel title left, as-of stamp right. */
export function PanelHead({
  title,
  asOf,
  stale = false,
  right,
}: {
  title: string;
  asOf?: string | null;
  stale?: boolean;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-3 border-b border-border px-3 py-2">
      <h2 className="microlabel">{title}</h2>
      <div className="ml-auto flex items-baseline gap-3">
        {right}
        {asOf != null && <AsOf stamp={asOf} stale={stale} />}
      </div>
    </div>
  );
}

/**
 * Freshness stamp. Stale data must be VISIBLY amber, never silently green.
 * Pass stale=true when the caller's freshness threshold is exceeded.
 */
export function AsOf({ stamp, stale = false }: { stamp: string; stale?: boolean }) {
  return (
    <span className={cn("font-data text-[11px]", stale ? "text-stale" : "text-faint")}>
      as of {stamp}
      {stale ? " STALE" : ""}
    </span>
  );
}

const TRUST_STYLES: Record<string, string> = {
  PROVEN: "border-success text-success",
  SHADOW: "border-info text-info",
  WATCH: "border-muted-foreground text-muted-foreground",
};

/** Trust-tier pill (PROVEN / SHADOW / WATCH). Unknown tiers render WATCH-style. */
export function TrustPill({ tier }: { tier: string | null | undefined }) {
  const key = (tier ?? "WATCH").toUpperCase();
  return (
    <span
      className={cn(
        "border px-1.5 py-px text-[10px] font-bold tracking-wider",
        TRUST_STYLES[key] ?? TRUST_STYLES.WATCH,
      )}
    >
      {key}
    </span>
  );
}

/** Right-aligned tabular numeric cell content. */
export function Num({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-data tabular", className)}>{children}</span>;
}

/**
 * Signed delta with direction ink. Formats to `digits` decimals with an
 * explicit sign; near-zero (rounds to 0) stays neutral ink.
 */
export function Delta({ value, digits = 3 }: { value: number | null | undefined; digits?: number }) {
  if (value == null || Number.isNaN(value)) return <Num className="text-faint">--</Num>;
  const rounded = Number(value.toFixed(digits));
  const cls = rounded > 0 ? "text-up" : rounded < 0 ? "text-down" : "text-muted-foreground";
  const sign = rounded > 0 ? "+" : "";
  return <Num className={cls}>{`${sign}${value.toFixed(digits)}`}</Num>;
}

/** Status dot (fleet/feed health). */
export function Dot({ state = "ok" }: { state?: "ok" | "warn" | "bad" }) {
  const color =
    state === "ok" ? "bg-success" : state === "warn" ? "bg-warning" : "bg-danger";
  return <span className={cn("inline-block h-[7px] w-[7px] rounded-full", color)} />;
}
