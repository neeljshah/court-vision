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
  const { data, ageSec, isStale, isLoading, error } =
    useLiveData<PaperToday>(fetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC });

  const t: PaperToday | null = data;
  const placed = t?.placed ?? [];
  const dayUnits = t?.day_units ?? null;
  const loading = !t && isLoading && !error;
  const placedAvailable = t?.source === "today_route" && t.placed_available !== false;
  const historyNote = loading
    ? "Loading placed history..."
    : !placedAvailable
      ? (error ?? t?.reason ?? "Placed history unavailable.")
      : error ? `Showing last available placed history. ${error}` : null;

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
        stale={isStale || Boolean(error)}
        right={
          dayUnits != null ? (
            <span className="flex items-center gap-1 font-data text-[10px] text-muted-foreground">
              day <Delta value={dayUnits} digits={2} />u
            </span>
          ) : undefined
        }
      />
      <section aria-label="today's placed paper bets" className="p-4">
        {t && (
          <p className="mb-3 font-mono text-[11px] text-muted-foreground">
            Reported date: {t.date ?? "--"}
          </p>
        )}
        <p className="mb-3 text-[11px] text-muted-foreground">
          These are bets the system ACTUALLY STAKED in paper (placed=true) -- distinct
          from the full candidate board below, which lists every calibrated divergence
          regardless of whether it cleared the stake floor. UNITS only; PAPER; real-money DENY.
        </p>

        {historyNote && (
          <p role="status" className="mb-3 font-mono text-[11px] text-muted-foreground">
            {historyNote}
          </p>
        )}
        {placedAvailable && <PlacedBetsTable rows={placed} fallbackNote={null} />}
      </section>
    </Panel>
  );
}
