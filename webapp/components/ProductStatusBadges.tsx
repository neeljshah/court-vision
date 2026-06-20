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

import { useEffect, useState } from "react";
import { getProductStatus, type ProductStatus } from "@/lib/api";
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
  const [status, setStatus] = useState<ProductStatus | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getProductStatus(ctrl.signal)
      .then(setStatus)
      .catch(() => setStatus(null));
    return () => ctrl.abort();
  }, []);

  if (!status) {
    return (
      <div className="flex items-center gap-1.5" aria-label="product status loading">
        <Pill tone="grey" label="status ..." />
      </div>
    );
  }

  const honest = honestTone(status);
  const honestLabel =
    status.allHonest === null
      ? "all_honest: unknown"
      : status.allHonest
      ? "all_honest: TRUE"
      : "all_honest: FALSE";

  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="product status">
      <Pill tone={honest} label={honestLabel} />
      <Pill tone="amber" label={status.selfImproveLabel} />
      <Pill tone="amber" label={status.realMoney === "DENY" ? "real-money: DENY" : "real-money"} />
      {!compact && (
        <Pill
          tone={status.liveSports.length > 0 ? "green" : "grey"}
          label={
            status.liveSports.length > 0
              ? `live: ${status.liveSports.join(" / ")}`
              : "live: none right now"
          }
        />
      )}
    </div>
  );
}
