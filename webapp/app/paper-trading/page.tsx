"use client";

// /paper-trading -- WS2 paper-trading center.
// PRIMARY: /api/paper/trail (all rows: settled+open). Settled book shows
//   outcome / model_prob / model_ev / taken_book / CLV / units columns.
// OPEN: trail rows filtered client-side (status=open||!graded).
// SECONDARY PM: /api/paper/pm/trail -- genuinely 0, honest-empty + LiveBadge.
// Per-venue VenueSummary: only renders rows that exist.
// UNITS/prob only. NO '$'. Real-money DENY. stale-never-green LiveBadge.

import { useCallback, useMemo, useState } from "react";
import type { PaperTrailRow } from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Badge, Unavailable } from "@/components/p6/Primitives";
import { PaperEquityPanel } from "@/components/paper/PaperEquityPanel";
import { LiveBadge } from "@/components/live/LiveBadge";
import { PmTrailTable } from "@/components/paper_pm/PmTrailTable";
import { PaperTrailSettled } from "@/components/paper_pm/PaperTrailSettled";
import { OpenPositions } from "@/components/paper_pm/OpenPositions";
import { VenueSummary } from "@/components/paper_pm/VenueSummary";
import { PanelErrorBoundary } from "@/components/p6/PanelErrorBoundary";
import { fmtPct, cn } from "@/lib/utils";
import {
  StatTile, deriveTally, deriveDoneSummary, toPaperTrailRows, mergeVenueRows,
  meanClvClass, EMPTY_CELL, fetchPaperCombined, type CombinedPayload,
} from "./paperTradingHelpers";

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function PaperTradingPage() {
  const fetcher = useCallback(fetchPaperCombined, []);

  const {
    data, ageSec, isStale, error, isLoading: loading,
  } = useLiveData<CombinedPayload>(fetcher, { intervalMs: 30_000, staleAfterSec: 90, cacheKey: "paper-trading:combined" });

  const [rankMode, setRankMode] = useState(false);

  const trail = data?.trail ?? null;
  const pmTrail = data?.pmTrail ?? null;
  const clv = data?.clv ?? null;
  const pnl = data?.pnl ?? null;
  const bankroll = data?.bankroll ?? null;

  // All trail rows from /api/paper/trail (open + settled, newest-first within bucket).
  const trailRows: PaperTrailRow[] = trail?.trail ?? [];

  // Scope filter: the full trail can be a firehose (hundreds of open props). "wc" isolates
  // World Cup activity (sport=soccer_intl: props + live in-game), "ingame" isolates live
  // in-game positions (channel=paper_ingame across sports). Pure client-side, no refetch.
  const [scope, setScope] = useState<"all" | "wc" | "ingame">("all");
  const viewRows: PaperTrailRow[] = useMemo(() => {
    if (scope === "wc") return trailRows.filter((r) => r.sport === "soccer_intl");
    if (scope === "ingame") return trailRows.filter((r) => r.channel === "paper_ingame");
    return trailRows;
  }, [trailRows, scope]);
  const scopeCounts = useMemo(() => ({
    all: trailRows.length,
    wc: trailRows.filter((r) => r.sport === "soccer_intl").length,
    ingame: trailRows.filter((r) => r.channel === "paper_ingame").length,
  }), [trailRows]);
  const pmTrades = pmTrail?.trades ?? [];
  const totalPm = pmTrail?.count ?? pmTrades.length;
  const tally = deriveTally(pmTrades);
  const pmRows = toPaperTrailRows(pmTrades);

  // venueRows: rows the per-venue execution breakdown aggregates -- the scope-filtered
  // trail UNION the PM trail, deduped (see mergeVenueRows). Shows sportsbooks + DFS prop
  // books + Kalshi/Polymarket + in-game, not just the PM trail.
  const venueRows = useMemo(() => mergeVenueRows(viewRows, pmRows), [viewRows, pmRows]);
  const isPmEmpty = !loading && pmTrail !== null && totalPm === 0;
  const doneSummary = deriveDoneSummary(trailRows);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Paper Trading Center</h1>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
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
        className="mb-5 rounded-lg border border-slate-800 bg-bg-subtle/60 px-4 py-2.5 text-[11px] text-muted-foreground"
      >
        <span className="font-semibold text-foreground">Units convention:</span>{" "}
        Stakes are in <span className="font-mono font-semibold">UNITS</span>, not dollars.
        Quarter-Kelly sizing -- a stake can exceed 1.0u when the model is highly confident.
        No dollar edge is claimed. CLV (beat-the-close) is the only honest calibration yardstick.
      </div>

      {/* BANKROLL + EQUITY CURVE -- "how much I would have made" in UNITS */}
      <PanelErrorBoundary label="bankroll and equity curve">
        <PaperEquityPanel series={pnl} bankroll={bankroll} loading={loading && !data} />
      </PanelErrorBoundary>

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
          valueClass={tally.nWin > 0 ? "text-success" : "text-foreground"} />
        <StatTile label="Loss" testId="tally-loss" loading={loading}
          value={loading ? EMPTY_CELL : String(tally.nLoss)}
          valueClass={tally.nLoss > 0 ? "text-danger" : "text-foreground"} />
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

      {/* SCOPE FILTER: All / World Cup / In-game -- de-noise the trail firehose */}
      <div
        data-testid="scope-filter"
        role="group"
        aria-label="Filter paper trail by scope"
        className="mb-4 flex flex-wrap items-center gap-2"
      >
        {([
          ["all", "All", scopeCounts.all],
          ["wc", "World Cup", scopeCounts.wc],
          ["ingame", "In-game (live)", scopeCounts.ingame],
        ] as const).map(([key, label, n]) => (
          <button
            key={key}
            type="button"
            data-testid={`scope-${key}`}
            onClick={() => setScope(key)}
            className={cn(
              "rounded-full border px-3 py-1 text-[11px] font-mono transition-colors",
              scope === key
                ? "border-amber-500/70 bg-amber-950/40 text-amber-300"
                : "border-border text-muted-foreground hover:bg-surface-2"
            )}
          >
            {label} ({n})
          </button>
        ))}
      </div>

      {/* OPEN POSITIONS: trail rows, OpenPositions filters status=open||!graded */}
      <section
        data-testid="open-positions-section"
        className="mb-6"
      >
        <h2
          aria-label="Open paper positions"
          className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground"
        >
          Open positions ({doneSummary.nOpen})
          {scope !== "all" ? ` -- ${scope === "wc" ? "World Cup" : "in-game"}` : ""}
        </h2>
        <PanelErrorBoundary label="open positions">
          <OpenPositions rows={viewRows} loading={loading && !trail} error={error} />
        </PanelErrorBoundary>
      </section>

      {/* PRIMARY: settled book -- outcome/model_prob/model_ev/taken_book/CLV/units */}
      <Panel
        title="Settled book (real paper record)"
        right={
          <span className="font-mono text-[10px] text-muted-foreground">
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
            <PaperTrailSettled rows={viewRows} loading={loading && !trail} error={error} settledOnly />
          )}
        </PanelErrorBoundary>
      </Panel>

      {/* DONE / SETTLED summary strip */}
      <section
        data-testid="done-settled-summary"
        aria-label="Done and settled summary"
        className="mb-5 mt-6"
      >
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          Done / settled summary
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <StatTile label="Total bets" testId="done-total" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nTotal)} />
          <StatTile label="Settled" testId="done-settled" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nSettled)} />
          <StatTile label="Win" testId="done-win" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nWin)}
            valueClass={doneSummary.nWin > 0 ? "text-success" : "text-foreground"} />
          <StatTile label="Loss" testId="done-loss" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nLoss)}
            valueClass={doneSummary.nLoss > 0 ? "text-danger" : "text-foreground"} />
          <StatTile label="Push" testId="done-push" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nPush)} />
          <StatTile label="Void" testId="done-void" loading={loading}
            value={loading ? EMPTY_CELL : String(doneSummary.nVoid)} />
          <StatTile label="Units staked" testId="done-units-staked" loading={loading}
            value={loading ? EMPTY_CELL : doneSummary.totalUnitsStaked.toFixed(2)} />
        </div>
      </section>

      {/* Per-venue execution breakdown -- real trail across every venue (sportsbooks +
          DFS prop books + Kalshi/Polymarket + live in-game). venueRows = mergeVenueRows. */}
      <section
        data-testid="venue-summary-section"
        aria-label="Per-venue paper trading summary"
        className="mb-5 mt-2"
      >
        <h2 className="mb-1 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          Per-venue breakdown{scope !== "all" ? ` -- ${scope === "wc" ? "World Cup" : "in-game"}` : ""}
        </h2>
        <p className="mb-3 text-[11px] text-faint">
          Where each paper bet executed -- best available price per market across
          sportsbooks, DFS prop books, Kalshi / Polymarket, and live in-game. Units only.
        </p>
        <PanelErrorBoundary label="venue summary">
          <VenueSummary rows={venueRows} loading={loading && !trail} error={error ?? null} />
        </PanelErrorBoundary>
      </section>

      {/* PM honest-empty: 0 liquid PM markets -- LiveBadge refresh still running */}
      {isPmEmpty && (
        <div
          data-testid="no-paper-trades"
          role="status"
          aria-label="No live PM game markets right now"
          className="mb-4 rounded-lg border border-slate-800 bg-bg-subtle/40 px-4 py-6 text-center text-sm text-muted-foreground"
        >
          <p data-testid="pm-empty-pm-game-markets" className="font-medium text-muted-foreground">
            No live PM game markets right now.
          </p>
          <p className="mt-1 text-xs text-faint">
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
                : "border-slate-700 text-muted-foreground hover:text-foreground"
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

      <p className="mt-4 text-[11px] text-faint">
        Paper mode -- stakes are units (no dollars). CLV (better-number-than-close) is
        the only honest calibration yardstick. No edge is claimed.
      </p>
    </div>
  );
}
