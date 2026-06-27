"use client";

// ProductStatusBadges -- the honest, product-wide status indicators rendered in
// the cohesive shell (Nav) and reused on the Home page status row.
//
// Surfaces, from REAL endpoints only (lib/api.getProductStatus):
//   * all_honest bit   -- GREEN when no face violates a rail; RED the instant one
//                         does (never hidden); GREY when the endpoint is
//                         unreachable (degrade, never green-on-missing).
//   * self-improve     -- "READY (not enabled)" -- the loop is INERT/human-gated.
//   * real-money       -- always "DENY" (paper only) in this build.
//
// NO $ field. Honest empty/unknown states. <= 300 LOC.

import { useCallback } from "react";
import { getProductStatus, type ProductStatus } from "@/lib/api";
import { useLiveData } from "@/lib/useLiveData";
import { cn } from "@/lib/utils";

type Tone = "green" | "amber" | "red" | "grey";

const DOT: Record<Tone, string> = {
  green: "bg-success",
  amber: "bg-warning",
  red: "bg-danger",
  grey: "bg-muted-foreground",
};

function Pill({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded border border-border",
        "bg-surface-1/70 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider",
        "text-muted-foreground",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", DOT[tone])} aria-hidden="true" />
      {label}
    </span>
  );
}

function honestTone(s: ProductStatus): Tone {
  if (s.allHonest === null) return "grey";
  return s.allHonest ? "green" : "red";
}

/**
 * Compact variant for the Nav (3 pills). `compact` hides the live-sports pill.
 */
export function ProductStatusBadges({ compact = false }: { compact?: boolean }) {
  // Poll + freshness-gate so the green "live:" pill cannot persist after the
  // predict endpoints go dead. getProductStatus degrades internally (never
  // throws), so it is a safe useLiveData fetcher.
  const fetcher = useCallback((signal: AbortSignal) => getProductStatus(signal), []);
  const { data: status, isStale, isLoading } = useLiveData<ProductStatus>(fetcher, {
    intervalMs: 30_000,
    staleAfterSec: 90,
  });

  if (!status) {
    return (
      <div className="flex items-center gap-1.5" aria-label="product status loading">
        <Pill tone="grey" label={isLoading ? "status ..." : "status unavailable"} />
      </div>
    );
  }

  // Stale data must never read green. Downgrade an otherwise-green honest bit to
  // amber when the feed is stale, and never show a green "live:" pill on stale.
  const honest = isStale && honestTone(status) === "green" ? "amber" : honestTone(status);
  const honestLabel =
    status.allHonest === null
      ? "all_honest: unknown"
      : status.allHonest
      ? isStale
        ? "all_honest: stale"
        : "all_honest: TRUE"
      : "all_honest: FALSE";

  const hasLive = status.liveSports.length > 0;
  // Green only when fresh AND live; stale-but-live shows amber "live: stale".
  const liveTone: Tone = hasLive ? (isStale ? "amber" : "green") : "grey";
  const liveLabel = !hasLive
    ? "live: none right now"
    : isStale
    ? `live: ${status.liveSports.join(" / ")} (stale)`
    : `live: ${status.liveSports.join(" / ")}`;

  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="product status">
      <Pill tone={honest} label={honestLabel} />
      <Pill tone="amber" label={status.selfImproveLabel} />
      <Pill tone="amber" label={status.realMoney === "DENY" ? "real-money: DENY" : "real-money"} />
      {!compact && <Pill tone={liveTone} label={liveLabel} />}
    </div>
  );
}
