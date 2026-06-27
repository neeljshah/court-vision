"use client";

// HomeTodayCard.tsx -- the "wake up and SEE everything for today" digest.
//
// Sits at the TOP of the Home page (and is mirrored at /today). At a glance:
//   - today's date + a stale-never-green freshness badge
//   - BEST BETS TODAY count (candidate board) + the system's PLACED (staked) bets
//   - YESTERDAY/SETTLED: W-L + day P&L (+/-X.Xu)
//   - the BANKROLL headline (current vs start units, net) + a compact equity sparkline
//   - today's self-improve decision (NO_CANDIDATE / SHIP)
//
// DATA: getPaperToday (/api/paper/today, falls back to pnl/series + bankroll),
//   /api/paper/pnl/series (sparkline points), /api/bestbets/board (candidate count),
//   /api/improve/status (self-improve decision). All via useLiveData (30s poll).
//
// HONESTY RAILS: UNITS only -- NO "$" token; edge_claimed=false; PAPER; real-money
// DENY; CLV is the yardstick (INSUFFICIENT_DATA at small-N); stale-never-green;
// degrades honestly when /api/paper/today is absent (placed feed unavailable note,
// never a fabricated placed bet). ASCII only. Under 300 LOC.

import { useCallback, useMemo } from "react";
import Link from "next/link";
import { useLiveData } from "@/lib/useLiveData";
import { getPaperToday, type PaperToday } from "@/lib/paperToday";
import { api, isUnavailable } from "@/lib/p5api";
import type { PnlSeries, ImproveStatus, BestBetsBoard, Unavailable } from "@/lib/types";
import { EquitySparkline } from "./EquitySparkline";
import {
  fmtUnits, fmtSignedUnits, signedUnitsClass, settledTally,
  resolveImproveDecision, PlacedBetsTable, digestDateLabel,
} from "./todayDigestHelpers";

const POLL_MS = 30_000;
const STALE_SEC = 90;

function StaleBadge({ ageSec, isStale }: { ageSec: number | null; isStale: boolean }) {
  if (ageSec === null) return null;
  const s = Math.max(0, ageSec);
  const label = s < 5 ? "just now" : s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`;
  return (
    <span className="font-mono text-[9px] uppercase tracking-wider text-slate-500" data-testid="today-age">
      updated {label}
      {isStale && (
        <span className="ml-1.5 text-amber-400" data-testid="today-stale">(stale)</span>
      )}
    </span>
  );
}

function StatTile({
  label, value, valueCls, sub, testId,
}: {
  label: string; value: string; valueCls?: string; sub?: string; testId?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-bg-subtle px-3 py-2.5">
      <div className="font-mono text-[9px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-0.5 font-mono text-lg tabular-nums ${valueCls ?? "text-slate-100"}`} data-testid={testId}>
        {value}
      </div>
      {sub ? <div className="mt-0.5 font-mono text-[9px] text-slate-600">{sub}</div> : null}
    </div>
  );
}

export function HomeTodayCard() {
  const todayFetcher = useCallback((signal: AbortSignal) => getPaperToday(signal), []);
  const pnlFetcher = useCallback((signal: AbortSignal) => api.getPaperPnlSeries(signal), []);
  const boardFetcher = useCallback((signal: AbortSignal) => api.bestbetsBoard({}, signal), []);
  const improveFetcher = useCallback((signal: AbortSignal) => api.improve(signal), []);

  const { data: today, ageSec, isStale, isLoading } =
    useLiveData<PaperToday>(todayFetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC });
  const { data: pnlRaw } =
    useLiveData<PnlSeries>(pnlFetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC });
  const { data: boardRaw } =
    useLiveData<BestBetsBoard>(boardFetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC });
  const { data: improveRaw } =
    useLiveData<ImproveStatus>(improveFetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC });

  const pnl: PnlSeries | null = pnlRaw && !isUnavailable(pnlRaw) ? (pnlRaw as PnlSeries) : null;
  const board: BestBetsBoard | null = boardRaw && !isUnavailable(boardRaw) ? (boardRaw as BestBetsBoard) : null;
  const improve: ImproveStatus | null = improveRaw && !isUnavailable(improveRaw) ? (improveRaw as ImproveStatus) : null;

  // candidate "BEST BETS TODAY" count -- pregame + live cards on the board.
  const bestBetsCount = useMemo(() => {
    if (!board?.cards) return null;
    return board.cards.filter((c) => c.status === "pregame" || c.status === "live").length;
  }, [board]);

  // equity sparkline points from the pnl series (cumulative bankroll over time).
  const sparkValues = useMemo(() => {
    const pts = pnl?.points ?? [];
    if (pts.length < 2) return null;
    return pts.map((p) => p.balance_units);
  }, [pnl]);

  const improveDecision = resolveImproveDecision(improve);

  if (isLoading && today === null) {
    return (
      <section className="mx-auto max-w-5xl px-4 pt-6 sm:px-6" aria-label="today digest loading" data-testid="today-card-loading">
        <div className="rounded-xl border border-slate-800 bg-bg-panel p-5">
          <div className="h-6 w-40 animate-pulse rounded bg-slate-700/40" />
        </div>
      </section>
    );
  }

  const t: PaperToday = today ?? {
    placed: [], pending: [], settled_today: [], day_units: null,
    cumulative_units: null, bankroll: null, start_units: null,
    source: "fallback", edge_claimed: false,
  };
  const tally = settledTally(t.settled_today);
  const net =
    t.bankroll != null && t.start_units != null ? t.bankroll - t.start_units : t.cumulative_units;
  const placedFallbackNote =
    t.source === "fallback" ? (t.reason ?? "placed-bet feed unavailable") : null;

  return (
    <section className="mx-auto max-w-5xl px-4 pt-6 sm:px-6" aria-label="today digest" data-testid="today-card">
      <div className="rounded-xl border border-slate-800 bg-bg-panel">
        {/* Header */}
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-5 py-3">
          <div className="flex items-baseline gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-200">
              Today -- what the system did
            </h2>
            <span className="font-mono text-[11px] text-slate-500" data-testid="today-date">
              {digestDateLabel(t)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <StaleBadge ageSec={ageSec} isStale={isStale} />
            <span className="rounded border border-amber-900/50 bg-amber-950/30 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-amber-400">
              paper -- units
            </span>
          </div>
        </header>

        <div className="p-5">
          {/* At-a-glance stat tiles */}
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatTile
              label="Best bets today"
              testId="today-bestbets-count"
              value={bestBetsCount != null ? String(bestBetsCount) : "--"}
              sub="candidate board"
            />
            <StatTile
              label="Placed (staked)"
              testId="today-placed-count"
              value={String(t.placed.length)}
              valueCls={t.placed.length > 0 ? "text-amber-300" : "text-slate-400"}
              sub="money-makers bet"
            />
            <StatTile
              label="Settled W-L"
              testId="today-settled-wl"
              value={`${tally.nWin} - ${tally.nLoss}`}
              sub={tally.nPush > 0 ? `${tally.nPush} push` : "graded today"}
            />
            <StatTile
              label="Day P&L"
              testId="today-day-pnl"
              value={`${fmtSignedUnits(t.day_units)}u`}
              valueCls={signedUnitsClass(t.day_units)}
              sub="paper, units"
            />
            <StatTile
              label="Self-improve"
              testId="today-improve"
              value={improveDecision.label}
              valueCls={improveDecision.tone === "ship" ? "text-emerald-400" : "text-slate-300"}
              sub={improveDecision.tone === "ship" ? "shipped" : "hold"}
            />
          </div>

          {/* BANKROLL headline + compact equity sparkline ("how much you'd have made") */}
          <div
            className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-800 bg-bg-subtle px-4 py-3"
            data-testid="today-bankroll"
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-mono text-[9px] uppercase tracking-wider text-slate-500">Bankroll</span>
              {t.bankroll != null && t.start_units != null ? (
                <>
                  <span className="font-mono text-2xl font-semibold tabular-nums text-slate-100">
                    {fmtUnits(t.bankroll)}
                  </span>
                  <span className="font-mono text-xs text-slate-500">/ {fmtUnits(t.start_units)} units</span>
                  {net != null && (
                    <span className={`font-mono text-sm font-semibold tabular-nums ${signedUnitsClass(net)}`} data-testid="today-net">
                      net {fmtSignedUnits(net)}u
                    </span>
                  )}
                </>
              ) : (
                <span className="font-mono text-xs text-slate-500">bankroll unavailable -- no paper book yet</span>
              )}
            </div>
            <div className="flex flex-col items-end gap-0.5">
              <EquitySparkline values={sparkValues} startUnits={t.start_units} />
              <span className="font-mono text-[8px] uppercase tracking-widest text-slate-600">
                paper equity (units)
              </span>
            </div>
          </div>

          {/* PLACED (staked) bets -- the money-makers the system actually bet */}
          <div className="mb-3" data-testid="today-placed-section">
            <div className="mb-2 flex items-center gap-2">
              <span className="rounded border border-amber-700/60 bg-amber-950/40 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-amber-300">
                placed
              </span>
              <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
                today&apos;s staked paper bets
              </span>
            </div>
            <PlacedBetsTable rows={t.placed} fallbackNote={placedFallbackNote} />
          </div>

          {/* CTAs + honest footer */}
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-800 pt-3">
            <Link href="/today" className="rounded-md border border-slate-700 px-3 py-1.5 font-mono text-[11px] text-slate-300 transition-colors hover:bg-accent/40" data-testid="cta-today">
              Full today view -&gt;
            </Link>
            <Link href="/bets" className="rounded-md border border-slate-700 px-3 py-1.5 font-mono text-[11px] text-slate-300 transition-colors hover:bg-accent/40" data-testid="cta-bets">
              Best bets board -&gt;
            </Link>
            <Link href="/paper-trading" className="rounded-md border border-slate-700 px-3 py-1.5 font-mono text-[11px] text-slate-300 transition-colors hover:bg-accent/40" data-testid="cta-paper">
              Full equity curve -&gt;
            </Link>
            <span className="ml-auto font-mono text-[9px] text-slate-600">
              PAPER -- units, not $. Real-money: DENY. CLV is the yardstick (INSUFFICIENT_DATA at small-N). No edge claimed.
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
