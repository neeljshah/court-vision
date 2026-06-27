"use client";

// PlacedBetsForGamePanel.tsx -- the EXECUTION-hand-in-hand headline for a game's
// card detail. While the ExecutionTrail below shows what the system WOULD do
// (line-shop -> devig -> decision), THIS panel shows what the system ACTUALLY
// STAKED for this game in the paper ledger: the placed bets with stake (units),
// tier, decision, settled outcome, and CLV grade -- each linking through to the
// per-bet execution detail at /paper/[betId].
//
// Data: GET /api/paper/trail (full open+settled trail) filtered to this game_id.
// useLiveData polling (pause-on-hidden, last-good, stale-never-green). No bespoke
// setInterval.
//
// HONESTY RAILS:
//   - UNITS only -- there is NO $ field / no $ P&L anywhere.
//   - decision=no_bet rows render explicitly (not silently dropped).
//   - outcome null -> "pending" (never a fabricated win/loss).
//   - CLV null / no_close / clv_unavailable -> INSUFFICIENT_DATA (never greened).
//   - Honest-empty when the system staked nothing for this game (the common,
//     calibration-success case): matching the efficient close is a no_bet.

import * as React from "react";
import { useCallback, useMemo } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { tierBadgeClass, EMPTY_CELL } from "@/lib/tokens";
import { Panel, Badge } from "@/components/p6/Primitives";
import { Empty, Unavailable } from "@/components/honest/HonestState";
import { useLiveData } from "@/lib/useLiveData";
import { api, isUnavailable } from "@/lib/p5api";
import type { PaperTrail, PaperTrailRow } from "@/lib/types";
import { toBetId } from "@/components/paper_pm/PmTradeRow";

export interface PlacedBetsForGamePanelProps {
  sport: string;
  gameId: string;
  className?: string;
}

type Outcome = "win" | "loss" | "push" | "void" | "pending";

function deriveOutcome(r: PaperTrailRow): Outcome {
  if (r.status === "open" || !r.graded) return "pending";
  const o = (r.outcome || "").toLowerCase();
  if (o === "win") return "win";
  if (o === "loss") return "loss";
  if (o === "push") return "push";
  return "void";
}

const OUTCOME_TONE: Record<Outcome, "green" | "red" | "slate" | "amber"> = {
  win: "green",
  loss: "red",
  push: "slate",
  void: "slate",
  pending: "amber",
};

function fmtUnits(u: number | null): string {
  return u != null && Number.isFinite(u) ? `${u.toFixed(2)}u` : EMPTY_CELL;
}

function fmtPct(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return EMPTY_CELL;
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}

// Selection label: prop -> "Player STAT line side"; game market -> "market side line".
function selectionLabel(r: PaperTrailRow): string {
  const mt = r.market_type ?? "moneyline";
  const lineStr = r.line != null ? ` ${r.line > 0 ? "+" : ""}${r.line}` : "";
  return `${mt}${lineStr} ${r.side}`.trim();
}

// CLV cell -- honest INSUFFICIENT_DATA, never greened on proxy/no-close.
function clvCell(r: PaperTrailRow): React.ReactNode {
  if (r.clv_unavailable || r.clv_status === "no_close" || r.clv_pct == null) {
    return (
      <span className="font-mono text-[10px] text-amber-600" data-testid="placed-clv">
        INSUFFICIENT_DATA
      </span>
    );
  }
  const beat = r.clv_pct >= 0;
  return (
    <span
      className={cn(
        "font-mono text-[10px]",
        beat ? "text-emerald-400" : "text-rose-400",
      )}
      data-testid="placed-clv"
    >
      {fmtPct(r.clv_pct)}
      {r.clv_is_proxy ? <span className="ml-1 text-amber-500">proxy</span> : null}
    </span>
  );
}

function PlacedBetRow({ r }: { r: PaperTrailRow }) {
  const outcome = deriveOutcome(r);
  const betId = toBetId(r);
  const isNoBet = (r.stake_units ?? 0) <= 0;
  return (
    <tr className="text-sm" data-testid="placed-bet-row">
      <td className="py-2 pr-3">
        <Link
          href={`/paper/${betId}`}
          className="font-medium text-slate-200 underline-offset-2 hover:text-slate-50 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-bg-panel"
          aria-label={`Execution detail: ${selectionLabel(r)}`}
        >
          {selectionLabel(r)}
        </Link>
        <div className="font-mono text-[10px] text-slate-500">
          {r.taken_book}
          {r.taken_decimal != null ? ` @ ${r.taken_decimal.toFixed(2)}` : ""}
        </div>
      </td>
      <td className="py-2 pr-3 text-right">
        <span
          className={cn(
            "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase",
            tierBadgeClass(r.tier ?? ""),
          )}
          data-testid="placed-tier"
        >
          {r.tier ?? EMPTY_CELL}
        </span>
      </td>
      <td className="py-2 pr-3 text-right">
        <span
          className="font-mono text-xs tabular-nums text-slate-100"
          data-testid="placed-units"
        >
          {isNoBet ? (
            <span className="text-slate-600">no_bet</span>
          ) : (
            fmtUnits(r.stake_units)
          )}
        </span>
      </td>
      <td className="py-2 pr-3 text-right">
        <Badge tone={OUTCOME_TONE[outcome]}>{outcome}</Badge>
      </td>
      <td className="py-2 text-right">{clvCell(r)}</td>
    </tr>
  );
}

/**
 * The placed-bets-for-this-game panel: what the system actually STAKED in the
 * paper ledger for this matchup (units / tier / outcome / CLV), each row linking
 * to its full execution detail. Honest-empty when nothing was staked.
 */
export function PlacedBetsForGamePanel({
  sport,
  gameId,
  className,
}: PlacedBetsForGamePanelProps) {
  const fetcher = useCallback(
    (s: AbortSignal) =>
      api.getPaperTrail({ sport, limit: 2000 }, s) as Promise<PaperTrail>,
    [sport],
  );
  const { data, isStale, error } = useLiveData<PaperTrail>(fetcher, {
    intervalMs: 30_000,
    staleAfterSec: 90,
  });

  const rows = useMemo<PaperTrailRow[]>(() => {
    if (!data || isUnavailable(data)) return [];
    return (data.trail ?? []).filter((r) => r.game_id === gameId);
  }, [data, gameId]);

  // Sort: staked-and-graded first, then staked-open, then no_bet rows.
  const sorted = useMemo(() => {
    const rank = (r: PaperTrailRow) => {
      const staked = (r.stake_units ?? 0) > 0;
      if (staked && r.graded) return 0;
      if (staked) return 1;
      return 2;
    };
    return [...rows].sort((a, b) => rank(a) - rank(b));
  }, [rows]);

  const staked = sorted.filter((r) => (r.stake_units ?? 0) > 0);
  const totalUnits = staked.reduce((n, r) => n + (r.stake_units ?? 0), 0);

  const headerRight = (
    <span className="font-mono text-[10px] text-slate-500">units only -- no $</span>
  );

  const firstLoadFailed = data == null && error != null;

  return (
    <Panel
      title="Placed bets (this game)"
      right={headerRight}
      className={className}
    >
      <p className="mb-2 text-[11px] leading-relaxed text-slate-500">
        What the system actually <strong className="text-slate-300">staked</strong> for
        this game in the paper ledger -- the money-makers. Stake is in{" "}
        <span className="font-mono">UNITS</span>; click a row for the full execution
        trail + CLV grade. Real money is{" "}
        <span className="font-mono uppercase text-amber-400">DENY</span>.
      </p>

      {isStale && data != null && (
        <div
          role="status"
          data-testid="placed-stale"
          className="mb-2 rounded border border-amber-900/40 bg-amber-950/20 px-2 py-1"
        >
          <span className="font-mono text-[10px] text-amber-400">
            showing last-good placed bets (poll stale)
          </span>
        </div>
      )}

      {firstLoadFailed ? (
        <Unavailable reason={error ?? "paper ledger unavailable"} />
      ) : staked.length === 0 ? (
        <Empty
          label="Nothing staked for this game"
          hint="The system placed no paper bet here -- matching the efficient close is a no_bet (a calibration success), not a missed opportunity."
        />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full" role="table">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
                  <th className="pb-2 font-medium">selection</th>
                  <th className="pb-2 text-right font-medium">tier</th>
                  <th className="pb-2 text-right font-medium">stake (u)</th>
                  <th className="pb-2 text-right font-medium">result</th>
                  <th className="pb-2 text-right font-medium">CLV</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {staked.map((r, i) => (
                  <PlacedBetRow key={`${toBetId(r)}-${i}`} r={r} />
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 flex items-center justify-between border-t border-slate-800 pt-2">
            <span className="font-mono text-[10px] text-slate-500">
              {staked.length} placed bet{staked.length !== 1 ? "s" : ""}
            </span>
            <span
              className="font-mono text-[11px] text-slate-300"
              data-testid="placed-total-units"
            >
              total staked: {totalUnits.toFixed(2)}u
            </span>
          </div>
        </>
      )}

      <p className="mt-3 text-[10px] leading-relaxed text-slate-600">
        Paper mode only -- "what the system would have staked to make the most
        (paper) units". No $ ROI is claimed; CLV = beat-the-close calibration
        yardstick and may be INSUFFICIENT_DATA without a true close.
      </p>
    </Panel>
  );
}
