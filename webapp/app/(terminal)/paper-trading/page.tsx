"use client";

// /paper-trading -- "Paper record": the forward paper book (29 fills), settled rows first.
// The July 2026 model-snapshot panels sit last, boxed and labelled; their slugs are
// sentinels since export_forward_record.py --with-sentinels (2026-10-20).
// PRIMARY: /api/paper/trail (all rows: settled+open). Settled book shows
//   outcome / model_prob / model_ev / taken_book / CLV / units columns.
// OPEN: trail rows filtered client-side (status=open||!graded).
// SECONDARY PM: /api/paper/pm/trail -- unavailable and empty are distinct.
// Per-venue VenueSummary: only renders rows that exist.
// UNITS/prob only. NO '$'. Real-money DENY. stale-never-green LiveBadge.

import { useCallback, useMemo, useState } from "react";
import { isSnapshotMode } from "@/lib/fetchHonest";
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
import { cn } from "@/lib/utils";
import { PaperTradingTally } from "./PaperTradingTally";
import { PaperTradingDoneSummary } from "./PaperTradingDoneSummary";
import { PaperRecordIntro, PaperOnlyBanner, UnitsClarifier, JulySnapshotBox } from "./PaperRecordNotes";
import {
  deriveTally, deriveDoneSummary, toPaperTrailRows, mergeVenueRows,
  EMPTY_CELL, fetchPaperCombined, type CombinedPayload,
} from "./paperTradingHelpers";

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
  const feedErrors = data?.errors ?? {};
  const partialError = Object.keys(feedErrors).length ? "Some paper data is unavailable" : null;
  const trailError = feedErrors.trail ?? error;
  const pmError = feedErrors.pmTrail ?? error;

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
  const tally = pmTrail ? deriveTally(pmTrades) : null;
  const pmRows = toPaperTrailRows(pmTrades);

  // venueRows: rows the per-venue execution breakdown aggregates -- the scope-filtered
  // trail UNION the PM trail, deduped (see mergeVenueRows). Shows sportsbooks + DFS prop
  // books + Kalshi/Polymarket + in-game, not just the PM trail.
  const venueRows = useMemo(() => mergeVenueRows(viewRows, pmRows), [viewRows, pmRows]);
  const isPmEmpty = !loading && pmTrail !== null && totalPm === 0;
  const doneSummary = trail ? deriveDoneSummary(trailRows) : null;

  const trailMeta = (trail ?? {}) as { as_of?: string; last_night?: string };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Paper record</h1>
          <PaperRecordIntro asOf={trailMeta.as_of ?? null} lastNight={trailMeta.last_night ?? null} />
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            Settled book first, then open fills and the venue breakdown. Units and probability only. No dollars.
            {!loading && pmTrail !== null && (
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
            {isSnapshotMode ? (
              <span className="font-data text-[12px] text-faint">
                as of {trailMeta.as_of ? trailMeta.as_of.slice(0, 10) : "not stated"}
              </span>
            ) : (
              <LiveBadge ageSec={partialError ? null : ageSec} isStale={isStale}
                error={error ?? partialError} isLoading={loading} />
            )}
          </span>
          <Badge tone="amber">paper mode</Badge>
        </div>
      </div>

      <PaperOnlyBanner />
      <UnitsClarifier />

      {/* PRIMARY: the 29-fill forward record, settled rows first */}
      <Panel
        title="Settled book (real paper record)"
        right={
          <span className="font-mono text-[12px] text-muted-foreground">
            {loading
              ? "loading"
              : !trail ? "unavailable"
              : `${trailRows.filter((r) => r.graded && r.status !== "open").length} settled / ${trailRows.length} total`}
          </span>
        }
      >
        <PanelErrorBoundary label="settled book">
          {trailError && !trail ? (
            <Unavailable reason={trailError} />
          ) : (
            <PaperTrailSettled rows={viewRows} loading={loading && !trail} error={trailError} settledOnly />
          )}
        </PanelErrorBoundary>
      </Panel>

      <PaperTradingDoneSummary summary={doneSummary} loading={loading} error={trailError} />

      <PaperTradingTally tally={tally} clv={clv} loading={loading} />

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
            disabled={!trail}
            onClick={() => setScope(key)}
            className={cn(
              "rounded-full border px-3 py-1 text-[12px] font-mono transition-colors",
              scope === key
                ? "border-warning/50 bg-warning/10 text-warning"
                : "border-border text-muted-foreground hover:bg-surface-2"
            )}
          >
            {label} ({trail ? n : EMPTY_CELL})
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
          className="mb-3 text-[12px] font-semibold uppercase tracking-widest text-muted-foreground"
        >
          Open positions ({doneSummary?.nOpen ?? EMPTY_CELL})
          {scope !== "all" ? ` -- ${scope === "wc" ? "World Cup" : "in-game"}` : ""}
        </h2>
        <PanelErrorBoundary label="open positions">
          <OpenPositions rows={viewRows} loading={loading && !trail} error={trailError} />
        </PanelErrorBoundary>
      </section>

      {/* Per-venue execution breakdown -- real trail across every venue (sportsbooks +
          DFS prop books + Kalshi/Polymarket + live in-game). venueRows = mergeVenueRows. */}
      <section
        data-testid="venue-summary-section"
        aria-label="Per-venue paper trading summary"
        className="mb-5 mt-2"
      >
        <h2 className="mb-1 text-[12px] font-semibold uppercase tracking-widest text-muted-foreground">
          Per-venue breakdown{scope !== "all" ? ` -- ${scope === "wc" ? "World Cup" : "in-game"}` : ""}
        </h2>
        <p className="mb-3 text-[12px] text-faint">
          Where each paper fill was recorded, by venue. Units only.
        </p>
        <PanelErrorBoundary label="venue summary">
          <VenueSummary rows={venueRows} loading={loading && !data} error={trailError ?? pmError ?? null} />
        </PanelErrorBoundary>
      </section>

      {/* PM honest-empty: 0 liquid PM markets -- LiveBadge refresh still running */}
      {isPmEmpty && (
        <div
          data-testid="no-paper-trades"
          role="status"
          aria-label="No live PM game markets right now"
          className="mb-4 rounded-lg border border-border bg-bg-subtle/40 px-4 py-6 text-center text-sm text-muted-foreground"
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
            className={`h-6 rounded-full border px-3 text-[12px] font-mono uppercase tracking-wide transition-colors ${
              rankMode
                ? "border-warning/50 bg-warning/10 text-warning"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {rankMode ? "ranked by tier" : "rank by tier"}
          </button>
        }
      >
        {pmError && !pmTrail ? (
          <PanelErrorBoundary label="PM trail table">
            <Unavailable reason={pmError} />
          </PanelErrorBoundary>
        ) : (
          <PanelErrorBoundary label="PM trail table">
            <PmTrailTable rows={pmRows} loading={loading} error={pmError} rankMode={rankMode} />
          </PanelErrorBoundary>
        )}
      </Panel>

      <JulySnapshotBox>
        {partialError && (
          <div role="status" aria-label="Unavailable paper data" className="mb-4 text-[12px] text-warning">
            Available summaries remain visible. Unavailable data:
            <ul>{([
              ["trail", "Trade history"], ["pmTrail", "PM trade history"],
              ["clv", "CLV summary"], ["pnl", "Equity history"], ["bankroll", "Bankroll"],
            ] as const).filter(([key]) => feedErrors[key]).map(([key, label]) => (
              <li key={key}>{label}: {feedErrors[key]}</li>
            ))}</ul>
          </div>
        )}
        <PanelErrorBoundary label="bankroll and equity curve">
          <PaperEquityPanel series={pnl} bankroll={bankroll} loading={loading && !data} />
        </PanelErrorBoundary>
      </JulySnapshotBox>

      <p className="mt-4 text-[12px] text-faint">
        Paper mode -- stakes are units (no dollars). No edge is claimed.
      </p>
    </div>
  );
}
