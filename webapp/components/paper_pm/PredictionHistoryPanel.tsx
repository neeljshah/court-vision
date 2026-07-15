"use client";

// PredictionHistoryPanel.tsx -- WS7 graded track-record panel for /paper.
//
// Polls GET /api/paper/predictions every 60s via useLiveData.
// AgeBadge bound to generated_at (stale-never-green -- amber on stale, NEVER green).
// Renders win/loss/pending graded rows with real final_score string.
// Honest "none settled yet" on empty. UNITS only -- NO $ / ROI / P&L field.
// No edge is claimed; calibration framing only.
//
// 300 LOC rail: this file stays under 300 lines.

import { useCallback } from "react";
import { api, type PaperPredictions } from "@/lib/p5api";
import type { PaperPredictionRow, Unavailable } from "@/lib/types";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Badge, Unavailable as UnavailablePanel } from "@/components/p6/Primitives";
import { AgeBadge } from "@/components/bets/BestBetsBoard";
import { fmtPct, tierClass } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";
import { humanizeMatchup, describeBetShort } from "@/lib/betdesc";

// ---------------------------------------------------------------------------
// PredictionHistoryRow -- one table row. UNITS only; no $ anywhere.
// pending = outcome is null (not yet graded).
// ---------------------------------------------------------------------------

function outcomeLabel(row: PaperPredictionRow): string {
  if (!row.outcome) return "pending";
  switch (row.outcome.toLowerCase()) {
    case "win":  return "WIN";
    case "loss": return "LOSS";
    case "push": return "PUSH";
    case "void": return "VOID";
    default:     return row.outcome.toUpperCase();
  }
}

function outcomeCls(row: PaperPredictionRow): string {
  if (!row.outcome) return "text-slate-500 italic";
  switch (row.outcome.toLowerCase()) {
    case "win":  return "text-success";
    case "loss": return "text-danger";
    default:     return "text-slate-400";
  }
}

function PredictionHistoryRow({ row }: { row: PaperPredictionRow }) {
  const probStr    = row.model_prob    != null ? `${(row.model_prob * 100).toFixed(1)}%`    : EMPTY_CELL;
  const unitsStr   = row.stake_units   != null ? `${row.stake_units.toFixed(2)}u`            : EMPTY_CELL;
  const marketStr  = row.market_prob   != null ? `${(row.market_prob * 100).toFixed(1)}%`   : EMPTY_CELL;
  const edgeStr    = row.edge_vs_market != null ? fmtPct(row.edge_vs_market)                 : EMPTY_CELL;
  const tierCls    = row.tier ? tierClass(row.tier) : "bg-slate-800 text-slate-400 border-slate-700";
  const edgeCls    =
    row.edge_vs_market != null && row.edge_vs_market > 0 ? "text-success"
    : row.edge_vs_market != null && row.edge_vs_market < 0 ? "text-danger"
    : "text-slate-500";
  // final_score is the real game result string (e.g. "110-104") from the API.
  // null when the game is not yet settled -- shown as "pending" in the outcome cell.
  const scoreStr   = row.final_score ?? EMPTY_CELL;

  return (
    <tr
      data-testid="prediction-row"
      className="border-b border-slate-800/60 text-[11px] hover:bg-slate-800/20 transition-colors"
    >
      <td className="py-2 pr-3 pl-2 font-mono text-slate-200">
        {humanizeMatchup(row.matchup)}
        {row.sport ? <span className="ml-1 text-slate-600 uppercase text-[9px]">{row.sport}</span> : null}
      </td>
      <td className="py-2 pr-3 font-mono text-slate-400">
        {describeBetShort(row)}
      </td>
      <td className="py-2 pr-3 font-mono tabular-nums text-slate-200">{probStr}</td>
      <td className="py-2 pr-3 font-mono tabular-nums text-slate-500">{marketStr}</td>
      <td className={`py-2 pr-3 font-mono tabular-nums ${edgeCls}`}>{edgeStr}</td>
      <td className="py-2 pr-3">
        {row.tier ? (
          <span
            data-testid="pred-tier"
            className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase ${tierCls}`}
          >
            {row.tier}
          </span>
        ) : (
          <span className="text-slate-600 font-mono">{EMPTY_CELL}</span>
        )}
      </td>
      <td className="py-2 pr-3 font-mono tabular-nums text-slate-300">{unitsStr}</td>
      {/* final_score: real reported result string, never fabricated */}
      <td
        data-testid="pred-final-score"
        className="py-2 pr-3 font-mono tabular-nums text-slate-400"
      >
        {scoreStr}
      </td>
      <td
        data-testid="pred-outcome"
        className={`py-2 pr-2 font-mono font-semibold ${outcomeCls(row)}`}
      >
        {outcomeLabel(row)}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// PredictionHistoryPanel -- exported for /paper and for unit tests.
// Calibration framing: shows graded win/loss/pending rows with real final
// scores. No edge is claimed. UNITS only -- no $ / ROI / P&L.
// ---------------------------------------------------------------------------

export function PredictionHistoryPanel() {
  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<PaperPredictions | Unavailable> => {
      const result = await api.paperPredictions({ limit: 500 }, signal);
      return result as PaperPredictions | Unavailable;
    },
    [],
  );

  const { data, isStale, ageSec, error, isLoading } = useLiveData<PaperPredictions>(
    fetcher,
    { intervalMs: 60_000, staleAfterSec: 180 },
  );

  const preds       = data?.predictions ?? [];
  const generatedAt = data?.generated_at ?? null;
  const isEmpty     = !isLoading && preds.length === 0;
  const showSkeleton = isLoading && data === null;

  return (
    <Panel
      title="Model Track Record"
      right={
        <div className="flex items-center gap-2">
          {/* AgeBadge: amber when stale, slate otherwise. NEVER green. */}
          <AgeBadge asOf={generatedAt} />
          {isStale ? <Badge tone="amber">stale</Badge> : null}
        </div>
      }
    >
      {isStale && !showSkeleton ? (
        <p
          data-testid="pred-history-stale"
          className="mb-2 text-[10px] font-mono text-amber-400"
        >
          stale: {ageSec != null ? `${ageSec}s ago` : "checking"}
        </p>
      ) : null}

      {error && data === null ? (
        <UnavailablePanel reason={error} />
      ) : showSkeleton ? (
        <div className="space-y-2" aria-busy="true" aria-label="loading prediction history">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-7 w-full animate-pulse rounded bg-slate-800/50" role="presentation" />
          ))}
        </div>
      ) : isEmpty ? (
        /* Honest empty state -- neutral, never red, no fabricated edge/score claim */
        <div
          data-testid="pred-history-empty"
          className="py-6 text-center"
          aria-label="no prediction records yet"
        >
          <p className="text-[12px] text-slate-500">None settled yet</p>
          <p className="mt-1 text-[11px] text-slate-600">
            Graded records appear here as predictions settle. Calibration only
            -- no edge is claimed. Units only, never dollars.
          </p>
        </div>
      ) : (
        <div
          data-testid="pred-history-table"
          className="overflow-x-auto"
          aria-label="prediction history table"
        >
          <table className="w-full min-w-[640px]">
            <thead>
              <tr className="border-b border-slate-800 text-[9px] uppercase tracking-wide text-slate-600">
                <th className="pb-1.5 pr-3 pl-2 text-left font-medium">Matchup</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Market / Side</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Model %</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Market %</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Divergence</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Tier</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Units</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Score</th>
                <th className="pb-1.5 pr-2 text-left font-medium">Result</th>
              </tr>
            </thead>
            <tbody>
              {preds.map((row, idx) => (
                <PredictionHistoryRow
                  key={`${row.game_id}-${row.market_type ?? ""}-${idx}`}
                  row={row}
                />
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[10px] text-slate-600">
            Units = Kelly-sized stake, never dollars. Divergence = model probability
            minus devigged market probability. Score = real final score (pending when
            not yet settled). No edge is claimed.
          </p>
        </div>
      )}
    </Panel>
  );
}
