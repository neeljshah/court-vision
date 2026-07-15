"use client";

// TodayPlacedBets.tsx -- the PLACED (staked) bets section for /bets.
//
// Distinguishes the bets the system ACTUALLY STAKED (placed=true paper) from the
// full candidate board rendered below by BestBetsBoard. Pulls from getPaperToday
// (/api/paper/today -> placed[]); when that feed is absent it degrades honestly to
// a "placed-bet feed unavailable" note -- NEVER a fabricated placed bet, and never
// implies the candidate board cards were staked.
//
// HONESTY RAILS: UNITS only -- NO "$" token; PAPER; edge_claimed=false; real-money
// DENY; stale-never-green. ASCII only. Under 300 LOC.

import { useCallback, useMemo } from "react";
import { useLiveData } from "@/lib/useLiveData";
import { getPaperToday, type PaperToday } from "@/lib/paperToday";
import { PlacedBetsTable } from "@/components/home/todayDigestHelpers";
import { Panel, PanelHead, Delta } from "@/components/ui/terminal";

const POLL_MS = 30_000;
const STALE_SEC = 90;

export function TodayPlacedBets() {
  const fetcher = useCallback((s: AbortSignal) => getPaperToday(s), []);
  const { data, ageSec, isStale } =
    useLiveData<PaperToday>(fetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC });

  const t: PaperToday | null = data;
  const placed = t?.placed ?? [];
  const dayUnits = t?.day_units ?? null;
  const fallbackNote =
    t && t.source === "fallback" ? (t.reason ?? "placed-bet feed unavailable") : null;

  const s = ageSec == null ? null : Math.max(0, ageSec);
  const asOfStamp = useMemo(() => {
    if (s == null) return null;
    return new Date(Date.now() - s * 1000).toLocaleTimeString("en-US", { hour12: false });
  }, [s]);

  return (
    <Panel>
      <PanelHead
        title="Today's placed bets"
        asOf={asOfStamp}
        stale={isStale}
        right={
          dayUnits != null ? (
            <span className="flex items-center gap-1 font-data text-[10px] text-muted-foreground">
              day <Delta value={dayUnits} digits={2} />u
            </span>
          ) : undefined
        }
      />
      <section aria-label="today's placed paper bets" className="p-4">
        <p className="mb-3 text-[11px] text-muted-foreground">
          These are bets the system ACTUALLY STAKED in paper (placed=true) -- distinct
          from the full candidate board below, which lists every calibrated divergence
          regardless of whether it cleared the stake floor. UNITS only; PAPER; real-money DENY.
        </p>

        <PlacedBetsTable rows={placed} fallbackNote={fallbackNote} />
      </section>
    </Panel>
  );
}
