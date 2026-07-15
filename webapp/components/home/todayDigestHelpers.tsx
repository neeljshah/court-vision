"use client";

// todayDigestHelpers.tsx -- shared pieces for HomeTodayCard / the /today view.
// Formatters, the PLACED-bet row, the self-improve decision resolver, and the
// settled-today W-L tally. Keeps HomeTodayCard under the 300-LOC rail.
//
// HONESTY RAILS: UNITS only -- NO $ token; edge_claimed=false; INSUFFICIENT_DATA
// surfaced verbatim; stale-never-green. ASCII only.

import type { TodayBet, PaperToday } from "@/lib/paperToday";
import type { ImproveStatus } from "@/lib/types";
import { humanizeMatchup, describeBetShort } from "@/lib/betdesc";

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

export function fmtUnits(v: number | null | undefined): string {
  if (v == null) return "--";
  return v.toFixed(2);
}

export function fmtSignedUnits(v: number | null | undefined): string {
  if (v == null) return "--";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}`;
}

export function signedUnitsClass(v: number | null | undefined): string {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-up";
  if (v < 0) return "text-down";
  return "text-foreground";
}

export function fmtProb(p: number | null | undefined): string {
  if (p == null) return "--";
  return `${(p * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Settled-today W-L tally
// ---------------------------------------------------------------------------

export interface DayTally {
  nWin: number;
  nLoss: number;
  nPush: number;
}

export function settledTally(rows: TodayBet[]): DayTally {
  let nWin = 0;
  let nLoss = 0;
  let nPush = 0;
  for (const r of rows) {
    const o = (r.outcome ?? "").toLowerCase();
    if (o === "win") nWin += 1;
    else if (o === "loss") nLoss += 1;
    else if (o === "push") nPush += 1;
  }
  return { nWin, nLoss, nPush };
}

// ---------------------------------------------------------------------------
// Self-improve decision resolver -- maps ImproveStatus -> a terse honest label.
// NO_CANDIDATE / ship / rollback / INERT, never an edge claim.
// ---------------------------------------------------------------------------

export interface ImproveDecision {
  label: string;          // e.g. "NO_CANDIDATE", "SHIP v7", "INERT"
  detail: string;         // a short honest gloss
  tone: "ship" | "neutral";
}

export function resolveImproveDecision(
  status: ImproveStatus | null,
): ImproveDecision {
  if (!status || !status.ratchet) {
    return {
      label: "UNAVAILABLE",
      detail: "self-improve status feed offline",
      tone: "neutral",
    };
  }
  const r = status.ratchet;
  const decision = (r.last_decision ?? r.state ?? "").toString().toUpperCase();
  const shipped = r.shipped_version;
  if (decision.includes("SHIP") || decision.includes("PROMOTE")) {
    return {
      label: shipped != null ? `SHIP v${shipped}` : "SHIP",
      detail: "ratchet promoted a recalibration this cycle (paper, gate-gated)",
      tone: "ship",
    };
  }
  if (decision.includes("ROLLBACK") || decision.includes("REVERT")) {
    return {
      label: "ROLLBACK",
      detail: "ratchet rolled a candidate back (do-no-harm)",
      tone: "neutral",
    };
  }
  if (decision.includes("NO_CANDIDATE") || decision.includes("NO CANDIDATE")) {
    return {
      label: "NO_CANDIDATE",
      detail: "no candidate cleared the eval gate this cycle (an honest hold)",
      tone: "neutral",
    };
  }
  // Fall back to the raw state, surfaced verbatim, never greened.
  return {
    label: decision || "INERT",
    detail: r.reason ?? "self-improve loop measured-only / human-gated",
    tone: "neutral",
  };
}

// ---------------------------------------------------------------------------
// PlacedBetRow -- one STAKED paper bet (the system's money-maker). UNITS only.
// ---------------------------------------------------------------------------

export function PlacedBetRow({ bet }: { bet: TodayBet }) {
  const o = (bet.outcome ?? "pending").toLowerCase();
  const outcomeCls =
    o === "win"
      ? "text-up"
      : o === "loss"
        ? "text-down"
        : "text-muted-foreground";
  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-1.5 pr-3 text-xs text-foreground truncate max-w-[150px]">
        {humanizeMatchup(bet.matchup) || "--"}
      </td>
      <td className="py-1.5 pr-3 font-mono text-[11px] text-muted-foreground truncate max-w-[120px]">
        {describeBetShort({
          market_type: bet.market_type,
          side: bet.side,
          matchup: bet.matchup,
          prop_player: bet.prop_player,
          prop_stat: bet.prop_stat,
          prop_side: bet.prop_side,
          line: bet.line,
        })}
      </td>
      <td className="py-1.5 pr-3 font-mono text-[11px] text-foreground tabular-nums">
        {fmtProb(bet.model_prob)}
      </td>
      <td className="py-1.5 pr-3 font-mono text-[11px] text-muted-foreground">
        {bet.tier ?? "--"}
      </td>
      <td className="py-1.5 pr-3 font-mono text-[11px] text-amber-300 tabular-nums">
        {bet.stake_units != null ? `${fmtUnits(bet.stake_units)}u` : "--"}
      </td>
      <td className={`py-1.5 pr-3 font-mono text-[11px] font-medium ${outcomeCls}`}>
        {o}
        {bet.pnl_units != null && (o === "win" || o === "loss") ? (
          <span className="ml-1 text-faint">{fmtSignedUnits(bet.pnl_units)}u</span>
        ) : null}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// PlacedBetsTable -- header + rows; honest-empty when no placed bets.
// ---------------------------------------------------------------------------

export function PlacedBetsTable({
  rows,
  fallbackNote,
}: {
  rows: TodayBet[];
  fallbackNote?: string | null;
}) {
  if (rows.length === 0) {
    return (
      <p
        data-testid="today-placed-empty"
        className="font-mono text-[11px] text-faint"
      >
        {fallbackNote
          ? fallbackNote
          : "No bets STAKED today yet. The system stakes only when a calibrated " +
            "divergence clears the tier floor; a no-bet day is a calibration success."}
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[460px] text-left" data-testid="today-placed-table">
        <thead>
          <tr className="border-b border-border">
            {["Matchup", "Market/Side", "Model prob", "Tier", "Stake (u)", "Result"].map(
              (h) => (
                <th
                  key={h}
                  className="pb-1.5 pr-3 font-mono text-[9px] uppercase tracking-wider text-faint"
                >
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((b, i) => (
            <PlacedBetRow key={`${b.game_id ?? "x"}-${b.market_type ?? "m"}-${i}`} bet={b} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Source / freshness helpers
// ---------------------------------------------------------------------------

export function digestDateLabel(today: PaperToday): string {
  if (today.date) return today.date;
  return "today";
}
