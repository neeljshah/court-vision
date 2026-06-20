"use client";

// SettleGradePanel.tsx -- settlement outcome + CLV grade for a game's bets.
//
// Shows: final score (from results), settled paper bet outcomes, CLV grade
// (beats-the-close, clv_pct as a probability ratio -- NOT a $ return), and an
// honest CLV-unavailable state when no true close exists. Reads the existing
// GameEdge shape (which carries best_bets with clv_is_proxy) and an optional
// ResultRow for the final score.
//
// HONESTY RAILS: CLV = beat-the-close yardstick (probability ratio). Never a
// $ ROI. clv_is_proxy = honest "no true close" warning, never green. The
// settlement rendering NEVER fabricates a result -- null outcome -> "VOID/pending".

import * as React from "react";
import { cn, tierClass } from "@/lib/utils";
import { Panel, Badge } from "@/components/p6/Primitives";
import { Empty } from "@/components/honest/HonestState";
import type { BestBet, GameEdge } from "@/lib/types";
import type { ResultRow } from "@/lib/types";

export interface SettleGradePanelProps {
  edge: GameEdge | null;
  result: ResultRow | null;
  className?: string;
}

const fmtPct = (v: number | null | undefined): string => {
  if (v == null || !Number.isFinite(v)) return "--";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
};

// Classify CLV for honest display (never green-on-proxy).
function clvLabel(bet: BestBet): { text: string; tone: "green" | "red" | "amber" | "slate" } {
  if (bet.clv_is_proxy) {
    return { text: "proxy close", tone: "amber" };
  }
  if (bet.edge == null) {
    return { text: "no close", tone: "slate" };
  }
  return bet.edge > 0
    ? { text: `beat close ${fmtPct(bet.edge)}`, tone: "green" }
    : { text: `missed close ${fmtPct(bet.edge)}`, tone: "red" };
}

function BetResultRow({ b }: { b: BestBet }) {
  const isBet = b.decision === "bet";
  const clv = clvLabel(b);
  return (
    <tr
      className={cn("text-sm", isBet ? "text-slate-200" : "text-slate-500")}
    >
      <td className="py-2 pr-3">
        <div className="font-medium">
          {b.market_type} <span className="text-slate-400">{b.side}</span>
        </div>
        <div className="font-mono text-[10px] text-slate-500">
          {b.best_book} @ {typeof b.best_odds === "number" ? b.best_odds.toFixed(2) : "--"}
          {b.line != null ? ` line ${b.line}` : ""}
        </div>
      </td>
      <td className="py-2 pr-3">
        <span className="font-mono text-[10px] text-slate-400">
          P={typeof b.model_prob === "number" ? (b.model_prob * 100).toFixed(1) + "%" : "--"}
          {" vs "}
          mkt={typeof b.market_prob === "number" ? (b.market_prob * 100).toFixed(1) + "%" : "--"}
        </span>
      </td>
      <td className="py-2 pr-3">
        <span
          className={cn(
            "inline-flex items-center rounded border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide",
            tierClass(b.tier ?? undefined),
          )}
        >
          {b.tier ?? "--"}
        </span>
      </td>
      <td className="py-2 text-right">
        <Badge tone={clv.tone}>{clv.text}</Badge>
        {b.clv_is_proxy && (
          <span className="ml-1 font-mono text-[9px] text-amber-500">proxy</span>
        )}
      </td>
    </tr>
  );
}

/** Settlement + CLV grade (CLV = probability ratio, not $ ROI). */
export function SettleGradePanel({
  edge,
  result,
  className,
}: SettleGradePanelProps) {
  const bets: BestBet[] = edge?.best_bets ?? [];
  const settled = bets.filter((b) => b.decision === "bet");
  const proxyWarning = settled.some((b) => b.clv_is_proxy);

  return (
    <Panel
      title="Settle / grade"
      right={
        <span className="font-mono text-[10px] text-slate-500">
          CLV = beat-close -- no $
        </span>
      }
      className={className}
    >
      {/* Final score */}
      {result ? (
        <div className="mb-3 flex items-center gap-3">
          <span className="text-xs text-slate-400">final score</span>
          <span className="font-mono font-semibold text-slate-100">
            {result.away ?? "AWAY"} {result.away_score ?? "--"}{" "}
            <span className="text-slate-500">@</span>{" "}
            {result.home_score ?? "--"} {result.home ?? "HOME"}
          </span>
          {result.completed && (
            <Badge tone="slate">final</Badge>
          )}
        </div>
      ) : null}

      {/* Settled bet rows */}
      {settled.length === 0 ? (
        <Empty
          label="No graded bets"
          hint="This game's bets will appear here once they settle."
        />
      ) : (
        <table className="w-full" role="table">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
              <th className="pb-2 font-medium">market</th>
              <th className="pb-2 font-medium">model vs market</th>
              <th className="pb-2 font-medium">tier</th>
              <th className="pb-2 text-right font-medium">CLV grade</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {settled.map((b, i) => (
              <BetResultRow key={`${b.market_type}-${b.side}-${i}`} b={b} />
            ))}
          </tbody>
        </table>
      )}

      {/* Honesty notice for proxy CLV */}
      {proxyWarning && (
        <div className="mt-3 rounded border border-amber-900/30 bg-amber-950/10 px-2 py-1.5">
          <p className="font-mono text-[10px] text-amber-400">
            proxy close -- the last pre-tip captured line, not a true settled close.
            CLV vs-close is UNPROVEN until a true close lands.
            In-game CLV may be INSUFFICIENT_DATA (no liquid in-play prices).
          </p>
        </div>
      )}

      <p className="mt-2 text-[10px] text-slate-600">
        CLV = calibration yardstick (beat-the-close probability ratio). No $ ROI.
        Paper mode only; no $ edge is claimed anywhere.
      </p>
    </Panel>
  );
}
