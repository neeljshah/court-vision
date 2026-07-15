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
import { Panel, PanelHead, AsOf, Num } from "@/components/ui/terminal";

const POLL_MS = 30_000;
const STALE_SEC = 90;

function StatTile({
  label, value, valueCls, sub, testId,
}: {
  label: string; value: string; valueCls?: string; sub?: string; testId?: string;
}) {
  return (
    <div className="border border-border bg-surface-2 px-3 py-2.5">
      <div className="microlabel">{label}</div>
      <Num className={`mt-0.5 block text-lg ${valueCls ?? "text-foreground"}`}>
        <span data-testid={testId}>{value}</span>
      </Num>
      {sub ? <div className="mt-0.5 font-data text-[9px] text-faint">{sub}</div> : null}
    </div>
  );
}

export function HomeTodayCard() {
  const todayFetcher = useCallback((signal: AbortSignal) => getPaperToday(signal), []);
  const pnlFetcher = useCallback((signal: AbortSignal) => api.getPaperPnlSeries(signal), []);
  const boardFetcher = useCallback((signal: AbortSignal) => api.bestbetsBoard({}, signal), []);
  const improveFetcher = useCallback((signal: AbortSignal) => api.improve(signal), []);

  const { data: today, ageSec, isStale, isLoading } =
    useLiveData<PaperToday>(todayFetcher, { intervalMs: POLL_MS, staleAfterSec: STALE_SEC, cacheKey: "home:today" });
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
        <Panel className="p-5">
          <div className="h-6 w-40 animate-pulse bg-surface-2" />
        </Panel>
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
      <Panel>
        <PanelHead
          title="Today -- what the system did"
          asOf={
            ageSec == null
              ? null
              : ageSec < 5
                ? "just now"
                : ageSec < 60
                  ? `${Math.floor(ageSec)}s ago`
                  : `${Math.floor(ageSec / 60)}m ago`
          }
          stale={isStale}
          right={
            <span className="flex items-center gap-2">
              <span className="font-data text-[11px] text-faint" data-testid="today-date">
                {digestDateLabel(t)}
              </span>
              <span className="border border-warning px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider text-warning">
                paper - units
              </span>
            </span>
          }
        />

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
              valueCls={t.placed.length > 0 ? "text-primary" : "text-muted-foreground"}
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
              valueCls={improveDecision.tone === "ship" ? "text-up" : "text-foreground"}
              sub={improveDecision.tone === "ship" ? "shipped" : "hold"}
            />
          </div>

          {/* BANKROLL headline + compact equity sparkline ("how much you'd have made") */}
          <div
            className="mb-4 flex flex-wrap items-center justify-between gap-4 border border-border bg-surface-2 px-4 py-3"
            data-testid="today-bankroll"
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="microlabel">Bankroll</span>
              {t.bankroll != null && t.start_units != null ? (
                <>
                  <Num className="text-2xl font-semibold text-foreground">
                    {fmtUnits(t.bankroll)}
                  </Num>
                  <Num className="text-xs text-faint">/ {fmtUnits(t.start_units)} units</Num>
                  {net != null && (
                    <Num className={`text-sm font-semibold ${signedUnitsClass(net)}`}>
                      <span data-testid="today-net">net {fmtSignedUnits(net)}u</span>
                    </Num>
                  )}
                </>
              ) : (
                <span className="font-data text-xs text-faint">bankroll unavailable -- no paper book yet</span>
              )}
            </div>
            <div className="flex flex-col items-end gap-0.5">
              <EquitySparkline values={sparkValues} startUnits={t.start_units} />
              <span className="font-data text-[9px] uppercase tracking-widest text-faint">
                paper equity (units)
              </span>
            </div>
          </div>

          {/* PLACED (staked) bets -- the money-makers the system actually bet */}
          <div className="mb-3" data-testid="today-placed-section">
            <div className="mb-2 flex items-center gap-2">
              <span className="border border-primary bg-surface-2 px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider text-primary">
                placed
              </span>
              <span className="microlabel">
                today&apos;s staked paper bets
              </span>
            </div>
            <PlacedBetsTable rows={t.placed} fallbackNote={placedFallbackNote} />
          </div>

          {/* CTAs + honest footer */}
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-3">
            <Link href="/today" className="border border-border px-3 py-1.5 font-data text-[11px] text-muted-foreground transition-colors hover:bg-accent/40" data-testid="cta-today">
              Full today view -&gt;
            </Link>
            <Link href="/bets" className="border border-border px-3 py-1.5 font-data text-[11px] text-muted-foreground transition-colors hover:bg-accent/40" data-testid="cta-bets">
              Best bets board -&gt;
            </Link>
            <Link href="/paper-trading" className="border border-border px-3 py-1.5 font-data text-[11px] text-muted-foreground transition-colors hover:bg-accent/40" data-testid="cta-paper">
              Full equity curve -&gt;
            </Link>
            <span className="ml-auto font-data text-[9px] text-faint">
              PAPER -- units, not $. Real-money: DENY. CLV is the yardstick (INSUFFICIENT_DATA at small-N). No edge claimed.
            </span>
          </div>
        </div>
      </Panel>
    </section>
  );
}
