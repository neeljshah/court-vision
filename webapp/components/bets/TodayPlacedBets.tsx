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

import { useCallback } from "react";
import { useLiveData } from "@/lib/useLiveData";
import { getPaperToday, type PaperToday } from "@/lib/paperToday";
import { PlacedBetsTable, fmtSignedUnits, signedUnitsClass } from "@/components/home/todayDigestHelpers";

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
  const ageLabel =
    s == null ? "" : s < 5 ? "just now" : s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`;

  return (
    <section
      aria-label="today's placed paper bets"
      data-testid="bets-placed-section"
      className="rounded-xl border border-amber-900/40 bg-amber-950/10 p-4"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="rounded border border-amber-700/60 bg-amber-950/40 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-amber-300">
            placed
          </span>
          <h2 className="font-mono text-[11px] font-semibold uppercase tracking-widest text-slate-300">
            Today&apos;s placed bets -- the money-makers the system staked
          </h2>
        </div>
        <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-wider text-slate-500">
          {dayUnits != null && (
            <span className={signedUnitsClass(dayUnits)} data-testid="bets-placed-day-pnl">
              day {fmtSignedUnits(dayUnits)}u
            </span>
          )}
          {s != null && (
            <span data-testid="bets-placed-age">
              updated {ageLabel}
              {isStale && <span className="ml-1 text-amber-400">(stale)</span>}
            </span>
          )}
        </div>
      </div>

      <p className="mb-3 text-[11px] text-slate-400">
        These are bets the system ACTUALLY STAKED in paper (placed=true) -- distinct
        from the full candidate board below, which lists every calibrated divergence
        regardless of whether it cleared the stake floor. UNITS only; PAPER; real-money DENY.
      </p>

      <PlacedBetsTable rows={placed} fallbackNote={fallbackNote} />
    </section>
  );
}
