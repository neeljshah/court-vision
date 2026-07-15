"use client";

// RecordsTable.tsx -- W2-records-clv-deep records table.
// W2 additions: market_prob column, model-vs-market divergence cell,
//               per-row deep-link to /records/<game_id> execution detail.
// Columns: matchup | market/side | model % | mkt % | divergence | line |
//          tier | units | result | CLV (+clv_status).
// UNITS only -- NO $ / ROI / P&L token. ASCII only. Under 300 LOC rail.

import type { PaperPredictionRow } from "@/lib/types";
import { tierClass } from "@/lib/utils";
import { EMPTY_CELL } from "@/lib/tokens";
import { humanizeMatchup, describeBetShort } from "@/lib/betdesc";

// ---------------------------------------------------------------------------
// Helpers
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
    case "win":  return "text-emerald-400 font-semibold";
    case "loss": return "text-rose-400 font-semibold";
    case "push": return "text-slate-400";
    default:     return "text-slate-500";
  }
}

function clvDisplay(row: PaperPredictionRow): string {
  if (row.clv_pct == null) return EMPTY_CELL;
  const pct = (row.clv_pct * 100).toFixed(1);
  return row.clv_pct >= 0 ? `+${pct}%` : `${pct}%`;
}

function clvCls(row: PaperPredictionRow): string {
  if (row.clv_pct == null) return "text-slate-600";
  return row.clv_pct > 0 ? "text-emerald-400" : row.clv_pct < 0 ? "text-rose-400" : "text-slate-400";
}

function clvStatusLabel(status: string | null): string {
  if (!status) return "";
  switch (status) {
    case "true_close":   return "close";
    case "proxy":        return "proxy";
    case "no_close":     return "no-close";
    default:             return status;
  }
}

/** market_prob formatted as a percentage string or EMPTY_CELL. */
function fmtMarketProb(v: number | null | undefined): string {
  if (v == null) return EMPTY_CELL;
  return `${(v * 100).toFixed(1)}%`;
}

/**
 * Divergence = model_prob - market_prob.
 * Positive means model is MORE confident than the market.
 * Returns "--" when either value is absent.
 */
function fmtDivergence(model: number | null | undefined, market: number | null | undefined): string {
  if (model == null || market == null) return EMPTY_CELL;
  const d = model - market;
  const s = (d * 100).toFixed(1);
  return d >= 0 ? `+${s}pp` : `${s}pp`;
}

function divergenceCls(model: number | null | undefined, market: number | null | undefined): string {
  if (model == null || market == null) return "text-slate-600";
  const d = model - market;
  return d > 0.03 ? "text-emerald-400" : d < -0.03 ? "text-rose-400" : "text-slate-400";
}

/**
 * buildPaperBetId -- encode a PaperPredictionRow into the /paper/[betId] segment.
 * Mirrors the toBetId pattern from PmTradeRow: sport|game_id|market|side.
 * No taken_book field on PaperPredictionRow, so we omit it (trail lookup
 * falls back to prefix match on sport|game_id in matchRow).
 * Returns null when game_id is absent (no link rendered).
 */
function buildPaperBetId(row: PaperPredictionRow): string | null {
  if (!row.game_id) return null;
  const parts = [
    row.sport        || "unknown",
    row.game_id,
    row.market_type  || "moneyline",
    row.side         || "home",
  ];
  return encodeURIComponent(parts.join("|"));
}

// ---------------------------------------------------------------------------
// RecordsRow -- one row in the table
// ---------------------------------------------------------------------------

function RecordsRow({ row }: { row: PaperPredictionRow }) {
  const probStr    = row.model_prob  != null ? `${(row.model_prob  * 100).toFixed(1)}%` : EMPTY_CELL;
  const mktStr     = fmtMarketProb(row.market_prob);
  const divStr     = fmtDivergence(row.model_prob, row.market_prob);
  const divCls     = divergenceCls(row.model_prob, row.market_prob);
  const unitsStr   = row.stake_units != null ? `${row.stake_units.toFixed(2)}u`          : EMPTY_CELL;
  const lineStr    = row.line        != null ? String(row.line)                           : EMPTY_CELL;
  const tierCls    = row.tier ? tierClass(row.tier) : "bg-slate-800 text-slate-400 border-slate-700";
  const clvStr     = clvDisplay(row);
  const clvC       = clvCls(row);
  const statusLbl  = clvStatusLabel(row.clv_status ?? null);

  // Per-row deep-link to /paper/[betId] execution detail page (W5).
  // If game_id is absent, no link is rendered (matchup shown as plain text).
  const betId = buildPaperBetId(row);
  const detailHref = betId ? `/paper/${betId}` : null;

  return (
    <tr
      data-testid="records-row"
      className="border-b border-slate-800/60 text-[11px] hover:bg-slate-800/20 transition-colors"
    >
      {/* Matchup + sport tag + deep-link */}
      <td className="py-2 pr-3 pl-2 font-mono text-slate-200">
        {detailHref ? (
          <a
            href={detailHref}
            data-testid="records-row-link"
            className="hover:underline hover:text-slate-100 transition-colors"
            aria-label={`View detail for ${humanizeMatchup(row.matchup ?? row.game_id)}`}
          >
            <span data-testid="records-matchup">{humanizeMatchup(row.matchup)}</span>
          </a>
        ) : (
          <span data-testid="records-matchup">{humanizeMatchup(row.matchup)}</span>
        )}
        {row.sport
          ? <span className="ml-1 font-mono text-[9px] uppercase text-slate-600">{row.sport}</span>
          : null}
      </td>

      {/* Market / Side -- human bet description (props, team ML, totals, spread) */}
      <td className="py-2 pr-3 font-mono text-slate-400">
        {describeBetShort(row)}
      </td>

      {/* model_prob as percentage */}
      <td
        data-testid="records-model-prob"
        className="py-2 pr-3 font-mono tabular-nums text-slate-200"
      >
        {probStr}
      </td>

      {/* market_prob as percentage (W2 addition) */}
      <td
        data-testid="records-market-prob"
        className="py-2 pr-3 font-mono tabular-nums text-slate-400"
      >
        {mktStr}
      </td>

      {/* model-vs-market divergence (W2 addition) */}
      <td
        data-testid="records-divergence"
        className={`py-2 pr-3 font-mono tabular-nums ${divCls}`}
      >
        {divStr}
      </td>

      {/* line / fair odds (line number from the market, not a $ figure) */}
      <td
        data-testid="records-line"
        className="py-2 pr-3 font-mono tabular-nums text-slate-500"
      >
        {lineStr}
      </td>

      {/* Tier badge */}
      <td className="py-2 pr-3">
        {row.tier
          ? (
            <span
              data-testid="records-tier"
              className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase ${tierCls}`}
            >
              {row.tier}
            </span>
          )
          : <span className="font-mono text-slate-600">{EMPTY_CELL}</span>
        }
      </td>

      {/* Units (Kelly-sized stake, never dollars) */}
      <td
        data-testid="records-units"
        className="py-2 pr-3 font-mono tabular-nums text-slate-300"
      >
        {unitsStr}
      </td>

      {/* Result */}
      <td
        data-testid="records-result"
        className={`py-2 pr-3 font-mono ${outcomeCls(row)}`}
      >
        {outcomeLabel(row)}
      </td>

      {/* CLV + clv_status */}
      <td className="py-2 pr-2">
        <span
          data-testid="records-clv"
          className={`font-mono tabular-nums ${clvC}`}
        >
          {clvStr}
        </span>
        {statusLbl
          ? (
            <span className="ml-1 font-mono text-[9px] text-slate-700">
              ({statusLbl})
            </span>
          )
          : null}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// RecordsTable -- exported table
// ---------------------------------------------------------------------------

interface RecordsTableProps {
  rows: PaperPredictionRow[];
}

export function RecordsTable({ rows }: RecordsTableProps) {
  return (
    <div
      data-testid="records-table"
      className="overflow-x-auto"
      aria-label="paper prediction records table"
    >
      <table className="w-full min-w-[860px]">
        <thead>
          <tr className="border-b border-slate-800 text-[9px] uppercase tracking-wide text-slate-600">
            <th scope="col" className="pb-1.5 pr-3 pl-2 text-left font-medium">Matchup</th>
            <th scope="col" className="pb-1.5 pr-3 text-left font-medium">Market / Side</th>
            <th scope="col" className="pb-1.5 pr-3 text-left font-medium">Model %</th>
            <th scope="col" className="pb-1.5 pr-3 text-left font-medium">Mkt %</th>
            <th scope="col" className="pb-1.5 pr-3 text-left font-medium">Divergence</th>
            <th scope="col" className="pb-1.5 pr-3 text-left font-medium">Line</th>
            <th scope="col" className="pb-1.5 pr-3 text-left font-medium">Tier</th>
            <th scope="col" className="pb-1.5 pr-3 text-left font-medium">Units</th>
            <th scope="col" className="pb-1.5 pr-3 text-left font-medium">Result</th>
            <th scope="col" className="pb-1.5 pr-2 text-left font-medium">CLV</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <RecordsRow
              key={`${row.game_id}-${row.market_type ?? ""}-${row.side}-${idx}`}
              row={row}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
