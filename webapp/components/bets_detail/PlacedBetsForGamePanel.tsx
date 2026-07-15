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
import { Badge } from "@/components/p6/Primitives";
import { Empty, Unavailable } from "@/components/honest/HonestState";
import { Panel as TerminalPanel, PanelHead, Num } from "@/components/ui/terminal";
import { useLiveData } from "@/lib/useLiveData";
import { api, isUnavailable } from "@/lib/p5api";
import type { PaperTrail, PaperTrailRow } from "@/lib/types";
import { toBetId } from "@/components/paper_pm/PmTradeRow";

export interface PlacedBetsForGamePanelProps {
  sport: string;
  gameId: string;
  className?: string;
}

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

// Format a fetch timestamp (ms epoch) as HH:MM:SS for the PanelHead as-of stamp.
function fmtClock(ms: number | null): string | null {
  if (ms == null) return null;
  return new Date(ms).toLocaleTimeString("en-US", { hour12: false });
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
      <span data-testid="placed-clv">
        <Num className="text-[10px] text-stale">INSUFFICIENT_DATA</Num>
      </span>
    );
  }
  const beat = r.clv_pct >= 0;
  return (
    <span data-testid="placed-clv">
      <Num className={cn("text-[10px]", beat ? "text-up" : "text-down")}>
        {fmtPct(r.clv_pct)}
      </Num>
      {r.clv_is_proxy ? <span className="ml-1 text-stale">proxy</span> : null}
    </span>
  );
}

function PlacedBetRow({ r }: { r: PaperTrailRow }) {
  const outcome = deriveOutcome(r);
  const betId = toBetId(r);
  const isNoBet = (r.stake_units ?? 0) <= 0;
  return (
    <tr className="text-sm hover:bg-surface-2" data-testid="placed-bet-row">
      <td className="py-1.5 px-3">
        <Link
          href={`/paper/${betId}`}
          className="font-medium text-foreground underline-offset-2 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
          aria-label={`Execution detail: ${selectionLabel(r)}`}
        >
          {selectionLabel(r)}
        </Link>
        <div className="font-data text-[10px] text-faint">
          {r.taken_book}
          {r.taken_decimal != null ? ` @ ${r.taken_decimal.toFixed(2)}` : ""}
        </div>
      </td>
      <td className="py-1.5 px-3 text-right">
        <span
          className={cn(
            "inline-flex items-center border px-2 py-0.5 font-data text-[10px] uppercase",
            tierBadgeClass(r.tier ?? ""),
          )}
          data-testid="placed-tier"
        >
          {r.tier ?? EMPTY_CELL}
        </span>
      </td>
      <td className="py-1.5 px-3 text-right">
        <span data-testid="placed-units">
          {isNoBet ? (
            <span className="font-data text-xs text-faint">no_bet</span>
          ) : (
            <Num className="text-xs text-foreground">{fmtUnits(r.stake_units)}</Num>
          )}
        </span>
      </td>
      <td className="py-1.5 px-3 text-right">
        <Badge tone={OUTCOME_TONE[outcome]}>{outcome}</Badge>
      </td>
      <td className="py-1.5 px-3 text-right">{clvCell(r)}</td>
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
  const { data, isStale, error, lastUpdatedAt } = useLiveData<PaperTrail>(fetcher, {
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
    <span className="font-data text-[10px] text-faint">units only -- no $</span>
  );

  const firstLoadFailed = data == null && error != null;

  return (
    <Panel
      title="Placed bets (this game)"
      asOf={fmtClock(lastUpdatedAt)}
      stale={isStale}
      right={headerRight}
      className={className}
    >
      <p className="mb-2 text-[11px] leading-relaxed text-faint">
        What the system actually <strong className="text-foreground">staked</strong> for
        this game in the paper ledger -- the money-makers. Stake is in{" "}
        <span className="font-data">UNITS</span>; click a row for the full execution
        trail + CLV grade. Real money is{" "}
        <span className="font-data uppercase text-stale">DENY</span>.
      </p>

      {isStale && data != null && (
        <div
          role="status"
          data-testid="placed-stale"
          className="mb-2 border border-warning/40 bg-warning/10 px-2 py-1"
        >
          <span className="font-data text-[10px] text-stale">
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
            <table className="w-full text-xs" role="table">
              <thead>
                <tr className="text-left">
                  <th className="microlabel py-1.5 px-3">selection</th>
                  <th className="microlabel py-1.5 px-3 text-right">tier</th>
                  <th className="microlabel py-1.5 px-3 text-right">stake (u)</th>
                  <th className="microlabel py-1.5 px-3 text-right">result</th>
                  <th className="microlabel py-1.5 px-3 text-right">CLV</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {staked.map((r, i) => (
                  <PlacedBetRow key={`${toBetId(r)}-${i}`} r={r} />
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 flex items-center justify-between border-t border-border pt-2">
            <span className="font-data text-[10px] text-faint">
              {staked.length} placed bet{staked.length !== 1 ? "s" : ""}
            </span>
            <span data-testid="placed-total-units">
              <Num className="text-[11px] text-foreground">total staked: {totalUnits.toFixed(2)}u</Num>
            </span>
          </div>
        </>
      )}

      <p className="mt-3 text-[10px] leading-relaxed text-faint">
        Paper mode only -- "what the system would have staked to make the most
        (paper) units". No $ ROI is claimed; CLV = beat-the-close calibration
        yardstick and may be INSUFFICIENT_DATA without a true close.
      </p>
    </Panel>
  );
}
