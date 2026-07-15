// SlateAgeBar -- per-sport slate age badge (FD-09).
// Shows "generated Xm ago" derived from PredictEnvelope.generated_at.
// Turns red when age > 30 min (stale-never-green rail).
//
// HONESTY RAILS: stale-never-green -- green ONLY when age <= 30 min;
// red with STALE prefix when age > 30 min; null generatedAt -> "no timestamp"
// (neutral slate, never fabricated fresh). NO $ anywhere.

import { timeAgoIso } from "@/components/p6/Primitives";
import { cn } from "@/lib/utils";

const STALE_AFTER_SEC = 30 * 60; // 30 min

function ageSeconds(generatedAt: string): number {
  const t = Date.parse(generatedAt);
  if (Number.isNaN(t)) return Infinity;
  return Math.max(0, (Date.now() - t) / 1000);
}

export function SlateAgeBar({
  generatedAt,
}: {
  generatedAt: string | null | undefined;
}) {
  if (!generatedAt) {
    return (
      <span aria-label="slate timestamp unavailable" className="font-data text-[11px] text-faint">
        no timestamp
      </span>
    );
  }

  const ageSec = ageSeconds(generatedAt);
  const isStale = ageSec > STALE_AFTER_SEC;
  const label = timeAgoIso(generatedAt);

  return (
    <span
      aria-label={isStale ? `slate stale: ${label}` : `slate generated ${label}`}
      className={cn("font-data text-[11px]", isStale ? "text-stale" : "text-faint")}
    >
      {isStale ? `STALE ${label}` : label}
    </span>
  );
}
