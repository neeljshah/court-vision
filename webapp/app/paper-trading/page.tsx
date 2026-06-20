"use client";

// /paper-trading -- WS2 paper-trading center.
// PRIMARY: /api/paper/trail (all rows: settled+open). Settled book shows
//   outcome / model_prob / model_ev / taken_book / CLV / units columns.
// OPEN: trail rows filtered client-side (status=open||!graded).
// SECONDARY PM: /api/paper/pm/trail -- genuinely 0, honest-empty + LiveBadge.
// Per-venue VenueSummary: only renders rows that exist.
// UNITS/prob only. NO '$'. Real-money DENY. stale-never-green LiveBadge.

import { useCallback, useState } from "react";
import { api, isUnavailable } from "@/lib/p5api";
import type { PaperTrail, PaperTrailRow, PmTrail, ClvScoreboard } from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import type { Unavailable as UnavailableSentinel } from "@/lib/types";
import { Panel, Badge, Unavailable } from "@/components/p6/Primitives";
import { LiveBadge } from "@/components/live/LiveBadge";
import { PmTrailTable } from "@/components/paper_pm/PmTrailTable";
import { PaperTrailSettled } from "@/components/paper_pm/PaperTrailSettled";
import { OpenPositions } from "@/components/paper_pm/OpenPositions";
import { VenueSummary } from "@/components/paper_pm/VenueSummary";
import { PanelErrorBoundary } from "@/components/p6/PanelErrorBoundary";
import { fmtPct } from "@/lib/utils";
import {
  StatTile, deriveTally, deriveDoneSummary, toPaperTrailRows,
  meanClvClass, EMPTY_CELL,
} from "./paperTradingHelpers";

// ---------------------------------------------------------------------------
// Combined fetcher payload
// ---------------------------------------------------------------------------

interface CombinedPayload {
  trail: PaperTrail | null;
  pmTrail: PmTrail | null;
  clv: ClvScoreboard | null;
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function PaperTradingPage() {
  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<CombinedPayload | UnavailableSentinel> => {
      const [t, pt, c] = await Promise.all([
        api.getPaperTrail({ limit: 2000 }, signal),
        api.pmTrail(undefined, signal),
        api.getPaperClv(signal),
      ]);
      if (isUnavailable(t)) {
        return {
          status: "unavailable",
          reason: (t as { reason?: string }).reason ?? "unavailable",
        } as UnavailableSentinel;
      }
      return {
        trail: t as PaperTrail,
        pmTrail: isUnavailable(pt) ? null : (pt as PmTrail),
        clv: isUnavailable(c) ? null : (c as ClvScoreboard),
      };
    },
    [],
  );

  const {
    data, ageSec, isStale, error, isLoading: loading,
  } = useLiveData<CombinedPayload>(fetcher, { intervalMs: 30_000, staleAfterSec: 90 });

  const [rankMode, setRankMode] = useState(false);

  const trail = data?.trail ?? null;
  const pmTrail = data?.pmTrail ?? null;
  const clv = data?.clv ?? null;

  // All trail rows (54 total: 46 settled + 8 open from /api/paper/trail).
  const trailRows: PaperTrailRow[] = trail?.trail ?? [];
  const pmTrades = pmTrail?.trades ?? [];
  const totalPm = pmTrail?.count ?? pmTrades.length;
  const tally = deriveTally(pmTrades);
  const pmRows = toPaperTrailRows(pmTrades);
  const isPmEmpty = !loading && pmTrail !== null && totalPm === 0;
  const doneSummary = deriveDoneSummary(trailRows);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Paper Trading Center</h1>
          <p className="mt-0.5 text-[12px] text-slate-500">
            Real settled book (primary) + Kalshi / Polymarket trail (secondary).
            Units and probability only. No dollars.
            {!loading && (
              <span
                data-testid="pm-total-count"
                aria-label={`PM trail total: ${totalPm} trade${totalPm !== 1 ? "s" : ""}`}
                className="ml-1 font-mono"
              >
                {totalPm > 0
                  ? `${totalPm} PM trade${totalPm !== 1 ? "s" : ""} in trail.`
                  : "No PM markets right now."}
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span data-testid="live-badge-placeholder">
            <LiveBadge ageSec={ageSec} isStale={isStale} error={error} isLoading={loading} />
          </span>
          <Badge tone="amber">paper mode</Badge>
        </div>
      </div>

      {/* Real-money DENY banner */}
      <div
        role="alert"
        data-testid="real-money-deny-banner"
        aria-label="Real money is DENIED -- paper mode only"
        className="mb-5 rounded-lg border border-amber-900/50 bg-amber-950/20 px-4 py-2.5 text-[11px] text-amber-400"
      >
        <span className="font-semibold">Real-money: DENY.</span>{" "}
        Paper mode only. No real money placed. Calibrated decision-support only.
        No dollar edge is claimed.
      </div>

      {/* Unit convention clarifier */}
      <div
        data-testid="unit-convention-clarifier"
        className="mb-5 rounded-lg border border-slate-800 bg-bg-subtle/60 px-4 py-2.5 text-[11px] text-slate-400"
      >
        <span className="font-semibold text-slate-300">Units convention:</span>{" "}
        Stakes are in <span className="font-mono font-semibold">UNITS</span>, not dollars.
        Quarter-Kelly sizing -- a stake can exceed 1.0u when the model is highly confident.
        No dollar edge is claimed. CLV (beat-the-close) is the only honest calibration yardstick.
      </div>

      {/* PM tally strip (running paper tally from PM trades) */}
      <div
        aria-label="Running paper tally"
        data-testid="running-tally"
        className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7"
      >
        <StatTile label="Open" testId="tally-open" loading={loading}
          value={loading ? EMPTY_CELL : String(tally.nOpen)} />
        <StatTile label="Settled" testId="tally-settled" loading={loading}
          value={loading ? EMPTY_CELL : String(tally.nSettled)} />
        <StatTile label="Win" testId="tally-win" loading={loading}
          value={loading ? EMPTY_CELL : String(tally.nWin)}
          valueClass={tally.nWin > 0 ? "text-success" : "text-slate-100"} />
        <StatTile label="Loss" testId="tally-loss" loading={loading}
          value={loading ? EMPTY_CELL : String(tally.nLoss)}
          valueClass={tally.nLoss > 0 ? "text-danger" : "text-slate-100"} />
        <StatTile label="Push" testId="tally-push" loading={loading}
          value={loading ? EMPTY_CELL : String(tally.nPush)} />
        <StatTile label="Units staked" testId="tally-units-staked" loading={loading}
          value={loading ? EMPTY_CELL : tally.unitsStaked.toFixed(2)} />
        <StatTile
          label="Mean CLV" testId="clv-mean-clv" loading={loading}
          valueClass={meanClvClass(clv)}
          value={
            loading ? EMPTY_CELL
            : clv?.mean_clv_pct != null ? fmtPct(clv.mean_clv_pct)
            : EMPTY_CELL
          }
        />
      </div>

      {/* OPEN POSITIONS: trail rows, OpenPositions filters status=open||!graded */}
      <section
        data-testid="open-positions-section"
        aria-label="Open paper positions"
        className="mb-6"
      >
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
          Open positions ({loading ? "..." : doneSummary.nOpen})
        </h2>
        <PanelErrorBoundary label="open positions">
          <OpenPositions rows={trailRows} loading={loading && !trail} error={error} />
        </PanelErrorBoundary>
      </section>

      {/* PRIMARY: settled book -- outcome/model_prob/model_ev/taken_book/CLV/units */}
      <Panel
        title="Settled book (real paper record)"
        right={
          <span className="font-mono text-[10px] text-slate-500">
            {loading
              ? "loading"
              : `${trailRows.filter((r) => r.graded && r.status !== "open").length} settled / ${trailRows.length} total`}
          </span>
        }
      >
        <PanelErrorBoundary label="settled book">
          {error && !trail ? (
            <Unavailable reason={error} />
          ) : (
            <PaperTrailSettled rows={trailRows} loading={loading && !trail} error={error} settledOnly />
          )}
        </PanelErrorBoundary>
      </Panel>

      {/* DONE / SETTLED summary strip */}
      <section
        data-testid="done-settled-summary"
        aria-label="Done and settled summary"
        className="mb-5 mt-6"
      >
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
          Done / settled summary
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <StatTile label="Total bets" testId="done-total" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nTotal)} />
          <StatTile label="Settled" testId="done-settled" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nSettled)} />
          <StatTile label="Win" testId="done-win" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nWin)}
            valueClass={doneSummary.nWin > 0 ? "text-success" : "text-slate-100"} />
          <StatTile label="Loss" testId="done-loss" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nLoss)}
            valueClass={doneSummary.nLoss > 0 ? "text-danger" : "text-slate-100"} />
          <StatTile label="Push" testId="done-push" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nPush)} />
          <StatTile label="Void" testId="done-void" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nVoid)} />
          <StatTile label="Units staked" testId="done-units-staked" loading={loading}
            value={loading ? EMPTY_CELL : doneSummary.totalUnitsStaked.toFixed(2)} />
        </div>
      </section>

      {/* Per-venue summary -- renders only venues with real rows */}
      <section
        data-testid="venue-summary-section"
        aria-label="Per-venue paper trading summary"
        className="mb-5 mt-2"
      >
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
          Per-venue breakdown
        </h2>
        <PanelErrorBoundary label="venue summary">
          <VenueSummary rows={pmRows} loading={loading} error={error ?? null} />
        </PanelErrorBoundary>
      </section>

      {/* PM honest-empty: 0 liquid PM markets -- LiveBadge refresh still running */}
      {isPmEmpty && (
        <div
          data-testid="no-paper-trades"
          role="status"
          aria-label="No live PM game markets right now"
          className="mb-4 rounded-lg border border-slate-800 bg-bg-subtle/40 px-4 py-6 text-center text-sm text-slate-500"
        >
          <p data-testid="pm-empty-pm-game-markets" className="font-medium text-slate-400">
            No live PM game markets right now.
          </p>
          <p className="mt-1 text-xs text-slate-600">
            Trades appear once the PM daemon places paper bets on live Kalshi / Polymarket markets.
            Executed: false. Real-money: DENY. No edge is claimed.
          </p>
        </div>
      )}

      {/* SECONDARY: PM trade trail (Kalshi / Polymarket) */}
      <Panel
        title="PM trade trail (Kalshi / Polymarket)"
        right={
          <button
            type="button"
            onClick={() => setRankMode((v) => !v)}
            className={`h-6 rounded-full border px-3 text-[10px] font-mono uppercase tracking-wide transition-colors ${
              rankMode
                ? "border-amber-700 bg-amber-950/40 text-amber-400"
                : "border-slate-700 text-slate-500 hover:text-slate-300"
            }`}
          >
            {rankMode ? "ranked: best first" : "rank by best trades"}
          </button>
        }
      >
        {error && !pmTrail ? (
          <PanelErrorBoundary label="PM trail table">
            <Unavailable reason={error} />
          </PanelErrorBoundary>
        ) : (
          <PanelErrorBoundary label="PM trail table">
            <PmTrailTable rows={pmRows} loading={loading} error={error} rankMode={rankMode} />
          </PanelErrorBoundary>
        )}
      </Panel>

      <p className="mt-4 text-[11px] text-slate-600">
        Paper mode -- stakes are units (no dollars). CLV (better-number-than-close) is
        the only honest calibration yardstick. No edge is claimed.
      </p>
    </div>
  );
}
