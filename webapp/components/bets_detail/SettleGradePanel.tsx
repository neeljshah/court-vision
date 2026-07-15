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
import { Badge } from "@/components/p6/Primitives";
import { Empty } from "@/components/honest/HonestState";
import { Panel as TerminalPanel, PanelHead, Num } from "@/components/ui/terminal";
import type { BestBet, GameEdge } from "@/lib/types";
import type { ResultRow } from "@/lib/types";

// Local Panel shim: p6/Primitives.Panel currently lacks asOf/stale wiring, so
// this component composes directly from the terminal.tsx primitives instead
// (same title/right/asOf/stale/children/className call shape used below).
function Panel({
  title,
  asOf,
  stale = false,
  right,
  children,
  className,
}: {
  title: string;
  asOf?: string | null;
  stale?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <TerminalPanel className={className}>
      <PanelHead title={title} asOf={asOf} stale={stale} right={right} />
      <div className="p-4">{children}</div>
    </TerminalPanel>
  );
}

export interface SettleGradePanelProps {
  edge: GameEdge | null;
  result: ResultRow | null;
  asOf?: string | null;
  stale?: boolean;
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
      className={cn("text-sm hover:bg-surface-2", isBet ? "text-foreground" : "text-faint")}
    >
      <td className="py-1.5 px-3">
        <div className="font-medium">
          {b.market_type} <span className="text-muted-foreground">{b.side}</span>
        </div>
        <div className="font-data text-[10px] text-faint">
          {b.best_book} @ <Num>{typeof b.best_odds === "number" ? b.best_odds.toFixed(2) : "--"}</Num>
          {b.line != null ? ` line ${b.line}` : ""}
        </div>
      </td>
      <td className="py-1.5 px-3">
        <Num className="text-[10px] text-muted-foreground">
          P={typeof b.model_prob === "number" ? (b.model_prob * 100).toFixed(1) + "%" : "--"}
          {" vs "}
          mkt={typeof b.market_prob === "number" ? (b.market_prob * 100).toFixed(1) + "%" : "--"}
        </Num>
      </td>
      <td className="py-1.5 px-3">
        <span
          className={cn(
            "inline-flex items-center border px-2 py-0.5 font-data text-[10px] font-semibold uppercase tracking-wide",
            tierClass(b.tier ?? undefined),
          )}
        >
          {b.tier ?? "--"}
        </span>
      </td>
      <td className="py-1.5 px-3 text-right">
        <Badge tone={clv.tone}>{clv.text}</Badge>
        {b.clv_is_proxy && (
          <span className="ml-1 font-data text-[9px] text-stale">proxy</span>
        )}
      </td>
    </tr>
  );
}

/** Settlement + CLV grade (CLV = probability ratio, not $ ROI). */
export function SettleGradePanel({
  edge,
  result,
  asOf,
  stale = false,
  className,
}: SettleGradePanelProps) {
  const bets: BestBet[] = edge?.best_bets ?? [];
  const settled = bets.filter((b) => b.decision === "bet");
  const proxyWarning = settled.some((b) => b.clv_is_proxy);

  return (
    <Panel
      title="Settle / grade"
      asOf={asOf}
      stale={stale}
      right={
        <span className="font-data text-[10px] text-faint">
          CLV = beat-close -- no $
        </span>
      }
      className={className}
    >
      {/* Final score */}
      {result ? (
        <div className="mb-3 flex items-center gap-3">
          <span className="text-xs text-muted-foreground">final score</span>
          <Num className="font-semibold text-foreground">
            {result.away ?? "AWAY"} {result.away_score ?? "--"}{" "}
            <span className="text-faint">@</span>{" "}
            {result.home_score ?? "--"} {result.home ?? "HOME"}
          </Num>
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
        <div className="overflow-x-auto">
          <table className="w-full text-xs" role="table">
            <thead>
              <tr className="text-left">
                <th className="microlabel py-1.5 px-3">market</th>
                <th className="microlabel py-1.5 px-3">model vs market</th>
                <th className="microlabel py-1.5 px-3">tier</th>
                <th className="microlabel py-1.5 px-3 text-right">CLV grade</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {settled.map((b, i) => (
                <BetResultRow key={`${b.market_type}-${b.side}-${i}`} b={b} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Honesty notice for proxy CLV */}
      {proxyWarning && (
        <div className="mt-3 border border-warning/40 bg-warning/10 px-2 py-1.5">
          <p className="font-data text-[10px] text-stale">
            proxy close -- the last pre-tip captured line, not a true settled close.
            CLV vs-close is UNPROVEN until a true close lands.
            In-game CLV may be INSUFFICIENT_DATA (no liquid in-play prices).
          </p>
        </div>
      )}

      <p className="mt-2 text-[10px] text-faint">
        CLV = calibration yardstick (beat-the-close probability ratio). No $ ROI.
        Paper mode only; no $ edge is claimed anywhere.
      </p>
    </Panel>
  );
}
