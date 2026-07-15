"use client";

// ExecutionDetail -- full execution detail for one PM paper trade.
// Shows: selection, model_prob, line, fair_odds, tier, units, result,
//        CLV+clv_status, taken_book, executed=false.
// NO $ P&L field. CLV honest: null/no-close shown as INSUFFICIENT_DATA.
// UNITS / probability only throughout.

import { cn } from "@/lib/utils";
import { fmtPct } from "@/lib/utils";
import { EMPTY_CELL, tierBadgeClass } from "@/lib/tokens";
import { Badge, Unavailable, Panel } from "@/components/p6/Primitives";
import { ClvInline } from "./ClvInline";
import { deriveResult } from "./PmTradeRow";
import { humanizeMatchup, describeBet } from "@/lib/betdesc";
import type { PaperTrailRow } from "@/lib/p5api";

function fmtProb(p: number | null): string {
  return p != null ? `${(p * 100).toFixed(1)}%` : EMPTY_CELL;
}

function fmtDec(d: number | null): string {
  return d != null ? d.toFixed(2) : EMPTY_CELL;
}

function fmtUnits(u: number | null): string {
  return u != null ? `${u.toFixed(2)}u` : EMPTY_CELL;
}

function fmtTs(iso: string | null): string {
  if (!iso) return EMPTY_CELL;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return EMPTY_CELL;
  return new Date(t).toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between border-b border-slate-800/60 py-2.5 last:border-0">
      <span className="text-[11px] uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <span className="text-right text-[12px] text-slate-200">{children}</span>
    </div>
  );
}

type Props = {
  row: PaperTrailRow | null;
  loading?: boolean;
  error?: string | null;
};

export function ExecutionDetail({ row, loading, error }: Props) {
  if (loading) {
    return (
      <Panel title="Execution detail">
        <p className="text-sm text-slate-500">loading...</p>
      </Panel>
    );
  }

  if (error || !row) {
    return (
      <Panel title="Execution detail">
        <Unavailable reason={error ?? "trade not found"} />
      </Panel>
    );
  }

  const res = deriveResult(row);
  const RESULT_TONE: Record<typeof res, "green" | "red" | "slate" | "amber"> =
    { win: "green", loss: "red", void: "slate", pending: "amber" };

  // Venue: PM-specific or taken_book raw
  const venue = (() => {
    const b = (row.taken_book || "").toLowerCase();
    if (b.includes("kalshi")) return "kalshi";
    if (b.includes("polymarket")) return "polymarket";
    const idx = row.taken_book?.indexOf(":") ?? -1;
    if (idx > 0) return row.taken_book!.slice(idx + 1);
    return row.taken_book || EMPTY_CELL;
  })();

  // Model EV: probability ratio p*odds-1, rendered as % (no $)
  const evDisplay =
    row.model_ev != null ? fmtPct(row.model_ev, true) : EMPTY_CELL;

  // Fair odds: 1 / model_prob (model-implied decimal price, unitless -- not a $ payout).
  const fairOdds =
    row.model_prob != null && row.model_prob > 0 && row.model_prob < 1
      ? (1 / row.model_prob).toFixed(3)
      : EMPTY_CELL;

  return (
    <Panel
      title="Execution detail"
      right={<Badge tone="amber">paper mode</Badge>}
    >
      <div className="space-y-0">
        {/* Selection: matchup + market + side (the traded position) */}
        <DetailRow label="Selection">
          <span data-testid="detail-selection" className="font-mono text-slate-100">
            {`${humanizeMatchup(row.matchup || row.game_id)} / ${describeBet(row)}`}
          </span>
        </DetailRow>
        <DetailRow label="Matchup">{humanizeMatchup(row.matchup || row.game_id)}</DetailRow>
        <DetailRow label="Sport">
          <span className="font-mono uppercase">{row.sport || EMPTY_CELL}</span>
        </DetailRow>
        <DetailRow label="Market">{row.market_type || EMPTY_CELL}</DetailRow>
        <DetailRow label="Side">{row.side || EMPTY_CELL}</DetailRow>

        {/* Tier / confidence */}
        <DetailRow label="Tier">
          {row.tier ? (
            <span
              data-testid="detail-tier"
              className={cn(
                "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase",
                tierBadgeClass(row.tier),
              )}
            >
              {row.tier}
            </span>
          ) : (
            <span data-testid="detail-tier">{EMPTY_CELL}</span>
          )}
        </DetailRow>

        {/* Venue / execution */}
        <DetailRow label="Venue">
          <span data-testid="detail-taken-book" className="font-mono">{venue}</span>
        </DetailRow>
        <DetailRow label="Line taken">
          <span data-testid="detail-line" className="font-mono">{fmtDec(row.taken_decimal)}</span>
        </DetailRow>

        {/* Model signal */}
        <DetailRow label="Model probability">
          <span data-testid="detail-model-prob" className="font-mono">{fmtProb(row.model_prob)}</span>
        </DetailRow>
        {/* Market probability: devigged market implied prob (null -> INSUFFICIENT_DATA). */}
        <DetailRow label="Market probability">
          <span data-testid="detail-market-prob" className="font-mono">
            {row.market_prob != null ? fmtProb(row.market_prob) : (
              <span className="text-[11px] text-amber-600">INSUFFICIENT_DATA</span>
            )}
          </span>
        </DetailRow>
        {/* Fair odds: 1/model_prob -- unitless decimal price, NOT a $ payout */}
        <DetailRow label="Fair odds (1/model_p, no $)">
          <span data-testid="detail-fair-odds" className="font-mono">{fairOdds}</span>
        </DetailRow>
        <DetailRow label="Model EV (prob, no $)">
          <span className="font-mono">{evDisplay}</span>
        </DetailRow>

        {/* Sizing -- UNITS not $ */}
        <DetailRow label="Stake (units, no $)">
          <span data-testid="detail-units" className="font-mono">{fmtUnits(row.stake_units)}</span>
        </DetailRow>

        {/* Result */}
        <DetailRow label="Result">
          <span data-testid="detail-result">
            <Badge tone={RESULT_TONE[res]}>{res}</Badge>
          </span>
        </DetailRow>
        {row.settled_at ? (
          <DetailRow label="Settled at">
            <span className="font-mono text-slate-400">
              {fmtTs(row.settled_at)}
            </span>
          </DetailRow>
        ) : null}

        {/* CLV -- honest: INSUFFICIENT_DATA when no close */}
        <DetailRow label="CLV (beat close?)">
          <span data-testid="detail-clv">
            {row.clv_unavailable || row.clv_status === "no_close" ? (
              <span className="font-mono text-[11px] text-amber-600">
                INSUFFICIENT_DATA
              </span>
            ) : (
              <ClvInline row={row} showStatus />
            )}
          </span>
        </DetailRow>
        <DetailRow label="CLV status">
          <span data-testid="detail-clv-status" className="font-mono text-[11px] text-slate-400">
            {row.clv_status || "no_close"}
          </span>
        </DetailRow>
        {row.clv_note ? (
          <DetailRow label="CLV note">
            <span className="text-[11px] text-slate-500">{row.clv_note}</span>
          </DetailRow>
        ) : null}

        {/* Channel -- always "paper" for this trail */}
        <DetailRow label="Channel">
          <span data-testid="detail-channel" className="font-mono text-[11px] text-slate-400">
            {row.channel ?? "paper"}
          </span>
        </DetailRow>

        {/* Executed -- always false; paper-only system */}
        <DetailRow label="Executed (real money)">
          <span
            data-testid="detail-executed"
            className="font-mono text-[11px] text-slate-600"
          >
            false (paper only)
          </span>
        </DetailRow>

        {/* Placed timestamp */}
        <DetailRow label="Placed at">
          <span className="font-mono text-slate-400">{fmtTs(row.ts)}</span>
        </DetailRow>
      </div>

      {/* Real-money DENY banner -- always shown; paper-only system */}
      <div
        data-testid="detail-real-money-deny"
        role="alert"
        aria-label="Real-money: DENY. Paper only -- no real money is placed."
        className="mt-4 flex items-center gap-2 rounded-lg border border-red-900/40 bg-red-950/20 px-3 py-2 text-[11px]"
      >
        <span className="font-mono font-semibold text-red-400">REAL-MONEY: DENY</span>
        <span className="text-slate-400">
          Paper only -- no real money is placed. Execution is always false.
        </span>
      </div>

      <p className="mt-4 text-[11px] leading-relaxed text-slate-600">
        Paper only. Stakes are units -- there is no dollar column. Model EV is a
        probability ratio (p * decimal_odds - 1), never a dollar amount. Fair odds
        = 1 / model_prob (unitless price ratio, not a $ payout). CLV is the only
        honest calibration yardstick; it may be INSUFFICIENT_DATA when no closing
        line was captured. No edge is claimed.
      </p>
    </Panel>
  );
}
