"use client";

import { useCallback, useMemo } from "react";
import {
  api,
  isUnavailable,
  type PaperTrail as PaperTrailEnvelope,
  type ClvScoreboard as Clv,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Unavailable, Badge } from "./Primitives";
import { Panel, PanelHead } from "@/components/ui/terminal";
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { cn, fmtPct } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";
import {
  clvCellClass,
  deriveResult,
  sportLabel,
  sortRows,
  type ResultFilter,
  type SortDir,
  type SortKey,
  type SportFilter,
} from "./paper-history-utils";
import {
  EmptyState,
  FilterGroup,
  SortHead,
  Stat,
  TableSkeleton,
  TradeRow,
} from "./PaperTradeRow";
import { useState } from "react";

// PaperHistory -- THE canonical paper-trade audit table. Renders EVERY paper
// trade (open + settled) from /api/paper/trail with sort + sport/result filters.
// UNITS / probability ONLY -- there is NO dollar column or $ field anywhere.
// A no-close / pending bet renders VOID/pending, NEVER a 0-fill win.
//
// Live polling: uses useLiveData (pause-on-hidden, last-good, stale badge).
// No bespoke setInterval anywhere in this component.

// Formats seconds into a human-readable age string.
function fmtAge(ageSec: number | null): string {
  if (ageSec === null) return "checking";
  if (ageSec < 60) return `${ageSec}s ago`;
  return `${Math.round(ageSec / 60)}m ago`;
}

export function PaperHistory() {
  const [sport, setSport] = useState<SportFilter>("all");
  const [result, setResult] = useState<ResultFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("ts");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Trail -- polled via useLiveData.
  const trailFetcher = useCallback(
    (s: AbortSignal) => api.getPaperTrail({ limit: 5000 }, s) as Promise<PaperTrailEnvelope>,
    [],
  );
  const {
    data: env,
    isLoading,
    error: trailErr,
    ageSec,
    isStale,
  } = useLiveData<PaperTrailEnvelope>(trailFetcher, {
    intervalMs: 30000,
    staleAfterSec: 120,
  });

  // CLV scoreboard -- polled separately so it updates independently.
  const clvFetcher = useCallback(
    (s: AbortSignal) => api.getPaperClv(s) as Promise<Clv>,
    [],
  );
  const { data: clv } = useLiveData<Clv>(clvFetcher, {
    intervalMs: 30000,
    staleAfterSec: 120,
  });

  const allRows = useMemo(() => env?.trail ?? [], [env]);

  const sportsAvailable = useMemo(() => {
    const set = new Set<string>();
    allRows.forEach((r) => r.sport && set.add(r.sport));
    return Array.from(set).sort();
  }, [allRows]);

  const filtered = useMemo(() => {
    let rows = allRows;
    if (sport !== "all") rows = rows.filter((r) => r.sport === sport);
    if (result !== "all")
      rows = rows.filter((r) => deriveResult(r) === result);
    return sortRows(rows, sortKey, sortDir);
  }, [allRows, sport, result, sortKey, sortDir]);

  const onSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "ts" || k === "clv_pct" ? "desc" : "asc");
    }
  };

  const clearFilters = () => {
    setSport("all");
    setResult("all");
  };
  const filtersActive = sport !== "all" || result !== "all";
  const settled = (clv?.n_bets ?? 0) > 0;
  const sortProps = { sortKey, sortDir, onSort };

  // Real fetch-time timestamp for the panel's as-of stamp -- never fabricated.
  const asOfIso =
    ageSec !== null ? new Date(Date.now() - ageSec * 1000).toISOString() : null;

  return (
    <Panel>
      <PanelHead
        title="Paper trade history"
        asOf={asOfIso}
        stale={isStale || !!trailErr}
        right={
          <span className="flex items-center gap-2">
            <Badge tone="amber">paper mode</Badge>
            <span className="font-data text-[10px] text-faint">
              units only - no $
            </span>
          </span>
        }
      />
      <div className="p-4">
      {/* CLV summary row (real zeros from API; no $ / ROI). */}
      <div className="mb-4 grid grid-cols-3 gap-3">
        <Stat
          label="Graded bets"
          value={isLoading && !clv ? null : String(clv?.n_bets ?? 0)}
        />
        <Stat
          label="% beat close"
          value={
            isLoading && !clv
              ? null
              : clv?.pct_beat_close != null
                ? fmtPct(clv.pct_beat_close, false)
                : EMPTY_CELL
          }
        />
        <Stat
          label="Mean CLV"
          value={
            isLoading && !clv
              ? null
              : clv?.mean_clv_pct != null
                ? fmtPct(clv.mean_clv_pct)
                : EMPTY_CELL
          }
          valueClass={clvCellClass(clv?.mean_clv_pct ?? null)}
        />
      </div>
      {!isLoading && !settled ? (
        <p className="mb-3 text-[11px] text-faint">
          No settled bets yet -- CLV populates as paper bets grade against the
          close. No edge is claimed.
        </p>
      ) : null}

      {/* Last-updated age (stale-never-green). */}
      <div
        className={cn(
          "mb-2 font-data text-[10px]",
          isStale ? "text-stale" : "text-faint",
        )}
        aria-label="trail-age"
      >
        {trailErr
          ? `unavailable -- ${trailErr}`
          : `updated ${fmtAge(ageSec)}${isStale ? " (stale)" : ""}`}
      </div>

      {/* Filter bar (local state only -- no API needed to render). */}
      <fieldset
        aria-label="Filter paper trades"
        className="mb-3 flex flex-wrap items-center gap-2 border-0 p-0"
      >
        <FilterGroup
          label="Sport"
          value={sport}
          onChange={setSport}
          options={["all", ...sportsAvailable]}
          render={(v) => (v === "all" ? "All" : sportLabel(v))}
        />
        <FilterGroup
          label="Result"
          value={result}
          onChange={(v) => setResult(v as ResultFilter)}
          options={["all", "win", "loss", "void", "pending"]}
          render={(v) => (v === "all" ? "All" : v)}
        />
        {filtersActive ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={clearFilters}
            className="h-6 px-2 text-[10px] text-faint"
          >
            clear filters
          </Button>
        ) : null}
        <span className="ml-auto font-data text-[10px] text-faint">
          {filtered.length} of {allRows.length} trades
        </span>
      </fieldset>

      {/* Table region -- degrades independently of the summary above. */}
      {isLoading ? (
        <TableSkeleton />
      ) : trailErr ? (
        <Unavailable reason={trailErr} />
      ) : allRows.length === 0 ? (
        <EmptyState message="No paper trades yet. The trail populates as the loop places paper bets." />
      ) : filtered.length === 0 ? (
        <EmptyState
          message="No paper trades match the current filters."
          onClear={filtersActive ? clearFilters : undefined}
        />
      ) : (
        <ScrollArea className="h-[600px] w-full border border-border">
          <Table role="grid" aria-label="Paper trade history">
            <caption className="sr-only">
              Paper trade history -- units and probability only, no dollar
              amounts.
            </caption>
            <TableHeader className="sticky top-0 z-10 bg-card">
              <TableRow className="border-border hover:bg-transparent">
                <SortHead label="Matchup" col="matchup" {...sortProps} />
                <SortHead label="Sport" col="sport" {...sortProps} />
                <SortHead label="Market" col="market_type" {...sortProps} />
                <TableHead className="microlabel h-9 px-3">
                  Side
                </TableHead>
                <SortHead label="Tier" col="tier" {...sortProps} />
                <SortHead label="Model P" col="model_prob" align="right" {...sortProps} />
                <SortHead label="Entry" col="taken_decimal" align="right" {...sortProps} />
                <SortHead label="CLV" col="clv_pct" align="right" {...sortProps} />
                <SortHead label="Result" col="result" {...sortProps} />
                <SortHead label="Units" col="stake_units" align="right" {...sortProps} />
                <SortHead label="Placed" col="ts" align="right" {...sortProps} />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r, i) => (
                <TradeRow
                  key={`${r.game_id}-${r.market_type}-${r.side}-${i}`}
                  row={r}
                />
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      )}

      <p className="mt-3 text-[11px] text-faint">
        Paper only -- stakes are units. There is no dollar column. No edge is
        claimed. CLV (better-number-than-close) is the only honest yardstick.
      </p>
      </div>
    </Panel>
  );
}
