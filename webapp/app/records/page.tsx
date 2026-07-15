"use client";

// app/records/page.tsx -- W1-records-server-paging: My Paper Bets / Records.
// TRUE server paging: fetch exactly {limit:50, offset} per page so all 3284
// rows are reachable. Pager total = envelopeTotal from API (e.g. 3284).
// Filters (sport/result/tier) applied client-side within the fetched page.
// W2 preserved: RecordsClvStrip + market_prob/divergence/deep-link columns.
// Honesty rails: UNITS only; stale-never-green; edge_claimed=false; no $.

import { useCallback, useEffect, useState, useMemo, useRef } from "react";
import { api } from "@/lib/p5api";
import type { PaperPredictions, Unavailable, PaperPredictionRow, ClvScoreboard, ClvSeries } from "@/lib/types";
import { useLiveData } from "@/lib/useLiveData";
import { Unavailable as UnavailablePanel } from "@/components/p6/Primitives";
import { AgeBadge } from "@/components/bets/BestBetsBoard";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { RecordsTable }        from "@/components/records/RecordsTable";
import { RecordsFilters, type RecordsFiltersState } from "@/components/records/RecordsFilters";
import { RecordsPager }         from "@/components/records/RecordsPager";
import { RecordsSummaryStrip }  from "@/components/records/RecordsSummaryStrip";
import { RecordsClvStrip }      from "@/components/records/RecordsClvStrip";
import { RecordsClvSeries }     from "@/components/records/RecordsClvSeries";
import { RecordsRollup }        from "@/components/records/RecordsRollup";

const PAGE_SIZE     = 50;
const POLL_INTERVAL = 30_000; // 30 s
const STALE_AFTER   = 120;    // 2 min

const DEFAULT_FILTERS: RecordsFiltersState = { sport: "all", result: "all", tier: "all" };

// Filter logic (client-side on the fetched page slice only)
function applyFilters(rows: PaperPredictionRow[], filters: RecordsFiltersState): PaperPredictionRow[] {
  return rows.filter((row) => {
    if (filters.sport  !== "all" && row.sport  !== filters.sport)  return false;
    if (filters.tier   !== "all" && row.tier   !== filters.tier)   return false;
    if (filters.result !== "all") {
      if (filters.result === "pending") {
        if (row.outcome != null) return false;
      } else {
        if ((row.outcome ?? "").toLowerCase() !== filters.result) return false;
      }
    }
    return true;
  });
}

export default function RecordsPage() {
  const [offset,  setOffset]  = useState(0);
  const [filters, setFilters] = useState<RecordsFiltersState>(DEFAULT_FILTERS);

  // TRUE server paging: fetch exactly PAGE_SIZE rows at the current offset.
  const predsFetcher = useCallback(
    async (signal: AbortSignal): Promise<PaperPredictions | Unavailable> =>
      (await api.getPaperPredictions({ limit: PAGE_SIZE, offset }, signal)) as PaperPredictions | Unavailable,
    [offset],
  );

  const { data, isStale, ageSec, error, isLoading, lastUpdatedAt, refresh } =
    useLiveData<PaperPredictions>(predsFetcher, { intervalMs: POLL_INTERVAL, staleAfterSec: STALE_AFTER, cacheKey: "records:preds" });

  // When offset changes, trigger an immediate server refetch (skip initial mount).
  const isMountedRef = useRef(false);
  useEffect(() => {
    if (!isMountedRef.current) { isMountedRef.current = true; return; }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset]);

  const pageRows      = data?.predictions ?? [];
  const generatedAt   = data?.generated_at ?? null;
  const envelopeTotal = data?.count ?? 0; // server's full count (e.g. 3284) -- pager total

  // Filters applied client-side within the fetched page; pager still shows envelopeTotal.
  const filteredRows = useMemo(() => applyFilters(pageRows, filters), [pageRows, filters]);
  const pagedRows  = filteredRows;
  const filtTotal  = filteredRows.length;
  const filtersActive = filters.sport !== "all" || filters.result !== "all" || filters.tier !== "all";

  const onFiltersChange = (next: RecordsFiltersState) => { setFilters(next); setOffset(0); };

  const showSkeleton = isLoading && data === null;
  const isEmpty      = !isLoading && filtTotal === 0;
  const hasError     = error != null && data === null;

  // CLV fetch (separate live feed, /api/paper/clv)
  const clvFetcher = useCallback(
    async (signal: AbortSignal): Promise<ClvScoreboard | Unavailable> =>
      (await api.getPaperClv(signal)) as ClvScoreboard | Unavailable,
    [],
  );
  const { data: clvData, isLoading: clvLoading, lastUpdatedAt: clvUpdatedAt } =
    useLiveData<ClvScoreboard>(clvFetcher, { intervalMs: POLL_INTERVAL, staleAfterSec: STALE_AFTER, cacheKey: "records:clv" });

  // CLV series fetch (sparkline, /api/paper/clv/series)
  const clvSeriesFetcher = useCallback(
    async (signal: AbortSignal): Promise<ClvSeries | Unavailable> =>
      (await api.getPaperClvSeries({}, signal)) as ClvSeries | Unavailable,
    [],
  );
  const { data: clvSeriesData, isLoading: clvSeriesLoading, lastUpdatedAt: clvSeriesUpdatedAt } =
    useLiveData<ClvSeries>(clvSeriesFetcher, { intervalMs: POLL_INTERVAL, staleAfterSec: STALE_AFTER, cacheKey: "records:clvseries" });

  // n_no_close from the CLV scoreboard (bets logged without a closing price yet)
  const nNoClose = (clvData as ClvScoreboard & { n_no_close?: number })?.n_no_close ?? undefined;

  // as-of stamps: real feed generated_at where available, else the local fetch time
  // recorded by useLiveData (CLV shapes carry no upstream timestamp of their own).
  const fmtAsOf = (iso: string | number | null | undefined): string | null =>
    iso == null ? null : new Date(iso).toLocaleTimeString();
  const predsAsOf     = fmtAsOf(generatedAt ?? lastUpdatedAt);
  const clvAsOf       = fmtAsOf(clvUpdatedAt);
  const clvSeriesAsOf = fmtAsOf(clvSeriesUpdatedAt);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 space-y-4">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[16px] font-semibold text-foreground tracking-tight">My Paper Bets / Records</h1>
          <p className="mt-0.5 font-data text-[11px] text-faint">
            {envelopeTotal > 0
              ? `${envelopeTotal} total predictions -- units only, no edge claimed`
              : "paper prediction record -- units only, no edge claimed"}
          </p>
        </div>
        {/* AgeBadge: stale-never-green */}
        <div className="flex items-center gap-2">
          <AgeBadge asOf={generatedAt} />
          {isStale && !showSkeleton && (
            <span className="font-data text-[10px] text-stale">
              stale: {ageSec != null ? `${ageSec}s ago` : "checking"}
            </span>
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={isLoading}
            aria-label="refresh records"
            className="border border-border bg-secondary px-2 py-1 font-data text-[10px] text-muted-foreground hover:text-foreground hover:border-ring disabled:opacity-40 transition-colors"
          >
            {isLoading ? "refreshing..." : "refresh"}
          </button>
        </div>
      </div>

      <RecordsClvStrip clv={clvData ?? null} loading={clvLoading && clvData === null} asOf={clvAsOf} />

      <RecordsClvSeries
        clvSeries={clvSeriesData ?? null}
        loading={clvSeriesLoading && clvSeriesData === null}
        nNoClose={nNoClose}
        asOf={clvSeriesAsOf}
      />

      {/* Filters + Pager row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <RecordsFilters value={filters} onChange={onFiltersChange} disabled={isLoading} />
          {/* Honest note: filters narrow the visible page, not the full dataset */}
          {filtersActive && (
            <p data-testid="records-filter-note" className="font-data text-[9px] text-faint">
              filtered within this page -- advance pages to see more
            </p>
          )}
        </div>
        <RecordsPager offset={offset} limit={PAGE_SIZE} total={envelopeTotal} onOffset={setOffset} disabled={isLoading} />
      </div>

      <RecordsSummaryStrip rows={pagedRows} total={envelopeTotal} loading={showSkeleton} asOf={predsAsOf} />

      <RecordsRollup rows={pagedRows} loading={showSkeleton} total={envelopeTotal} asOf={predsAsOf} />

      {/* Main panel */}
      <Panel>
        <PanelHead
          title={envelopeTotal > 0 ? `Records (${envelopeTotal} total)` : "Records"}
          asOf={predsAsOf}
          stale={isStale}
          right={<span className="font-data text-[9px] text-faint">calibration only -- not a market edge</span>}
        />
        <div className="px-4 py-3">
          {hasError ? (
            <UnavailablePanel reason={error ?? undefined} />
          ) : showSkeleton ? (
            <div className="space-y-2" aria-busy="true" aria-label="loading records" data-testid="records-loading">
              {Array.from({ length: 5 }, (_, i) => (
                <div key={i} className="h-7 w-full animate-pulse bg-surface-2" role="presentation" />
              ))}
            </div>
          ) : isEmpty ? (
            /* Honest empty state -- total===0, never hides real rows */
            <div data-testid="records-empty" className="py-10 text-center" aria-label="no records yet">
              <p className="text-[13px] text-faint">No records yet</p>
              <p className="mt-1 text-[11px] text-faint">
                {envelopeTotal === 0
                  ? "Predictions appear here once the model produces them and the service is running."
                  : "No records match the current filters on this page. Try clearing sport / result / tier or advance to another page."}
              </p>
              <p className="mt-2 font-data text-[10px] text-faint">Units only -- no edge is claimed. Calibration, not profit.</p>
            </div>
          ) : (
            <>
              <RecordsTable rows={pagedRows} />
              <p className="mt-2 font-data text-[10px] text-faint">
                Units = Kelly-sized stake, never dollars. CLV = beat-the-close
                (proxy = last pre-tip line; no-close = not gradeable). No edge is claimed.
              </p>
            </>
          )}
        </div>
      </Panel>

      {/* Bottom pager (convenience) -- always shown when server total > PAGE_SIZE */}
      {envelopeTotal > PAGE_SIZE && (
        <div className="flex justify-end">
          <RecordsPager offset={offset} limit={PAGE_SIZE} total={envelopeTotal} onOffset={setOffset} disabled={isLoading} />
        </div>
      )}

      {/* Auto-refresh indicator */}
      <p className="text-right font-data text-[9px] text-faint" aria-live="off" suppressHydrationWarning>
        {lastUpdatedAt
          ? `last refreshed: ${new Date(lastUpdatedAt).toLocaleTimeString()} -- auto-refreshes every 30s`
          : "waiting for first load..."}
      </p>
    </main>
  );
}
