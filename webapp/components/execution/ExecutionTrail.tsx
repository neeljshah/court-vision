"use client";

// ExecutionTrail -- shared cross-venue decision-trail surface (WS5).
//
// Renders: line-shopping table (all venues -> decimal odds) -> best line
// highlighted -> devig output -> no_bet/units/tier decision trail.
// Reusable from a bet card detail AND a PM paper trade.
//
// HONESTY RAILS:
//   - UNITS not $ anywhere (no dollar column, no dollar P&L).
//   - Real-money DENY note always visible.
//   - Devig shown as probability ratio (Shin-implied), never as $ edge.
//   - CLV may be INSUFFICIENT_DATA -- shown honestly, never fabricated.
//   - Empty / no book data -> honest unavailable state (never a guessed line).
//   - Best line = highest decimal odds (lowest vig) at last capture.
//   - Decision: no_bet / units / tier label only.

import * as React from "react";
import { cn } from "@/lib/utils";
import { tierBadgeClass, EMPTY_CELL } from "@/lib/tokens";
import { Panel, Badge, Unavailable } from "@/components/p6/Primitives";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type BookLineRow = {
  book: string;
  decimal_odds: number | null; // decimal price (never $ payout)
  line: number | null;
  is_pm?: boolean;
  captured_at?: string | null;
};
export type DevigResult = { fair_prob: number; vig_pct: number };
export type DecisionStep = "no_bet" | "bet" | string;
export type TierLabel = "S" | "A" | "B" | "C" | null;
export type ExecutionTrailProps = {
  bookLines: BookLineRow[];
  bestBook: string | null;
  devig: DevigResult | null;
  decision: DecisionStep | null;
  stakeUnits: number | null;
  tier: TierLabel;
  clvStatus: string | null;
  modelProb: number | null;
  decisionNote?: string | null;
  loading?: boolean;
  error?: string | null;
  className?: string;
};

// ---------------------------------------------------------------------------
// Private formatters (ASCII-safe -- no unicode)
// ---------------------------------------------------------------------------

const fmt2 = (v: number | null) =>
  v == null || !Number.isFinite(v) ? EMPTY_CELL : v.toFixed(2);

const fmtPct = (v: number) => `${(v * 100).toFixed(1)}%`;

const fmtLine = (l: number | null) =>
  l == null || !Number.isFinite(l) ? "" : ` (${l > 0 ? "+" : ""}${l})`;

const fmtUnits = (u: number | null) =>
  u == null ? EMPTY_CELL : `${u.toFixed(2)}u`;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function BookLinesTable({
  bookLines,
  bestBook,
}: {
  bookLines: BookLineRow[];
  bestBook: string | null;
}) {
  if (bookLines.length === 0) {
    return (
      <p className="py-2 text-xs text-slate-600" data-testid="no-book-lines">
        No book quotes captured yet.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto" data-testid="book-lines-table">
      <table className="w-full text-xs" role="table">
        <thead>
          <tr>
            {["book", "decimal odds", "line", "best"].map((h) => (
              <th
                key={h}
                className={cn(
                  "py-1 text-[10px] font-medium uppercase tracking-wide text-slate-500",
                  h === "book" ? "pr-3 text-left" : "px-2 text-right",
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/50">
          {bookLines.map((bl, i) => {
            const isBest = !!bestBook && bl.book === bestBook;
            return (
              <tr key={`${bl.book}-${i}`} data-testid={isBest ? "best-line-row" : undefined}>
                <td className="py-1.5 pr-3 font-mono text-slate-300">
                  {bl.book}
                  {bl.is_pm && (
                    <span className="ml-1 text-[9px] text-purple-400">PM</span>
                  )}
                </td>
                <td
                  className={cn(
                    "px-2 py-1.5 text-right font-mono tabular-nums",
                    isBest ? "font-semibold text-emerald-400" : "text-slate-300",
                  )}
                  title={bl.captured_at ? `captured ${bl.captured_at}` : undefined}
                >
                  {fmt2(bl.decimal_odds)}
                  {fmtLine(bl.line)}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-[10px] text-slate-500">
                  {bl.line != null ? fmtLine(bl.line) : EMPTY_CELL}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-[10px]">
                  {isBest ? (
                    <span
                      data-testid="best-badge"
                      className="rounded border border-emerald-900/50 bg-emerald-950/20 px-1 py-0.5 text-emerald-400"
                    >
                      best
                    </span>
                  ) : (
                    <span className="text-slate-700">{EMPTY_CELL}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DevigSection({ devig }: { devig: DevigResult | null }) {
  return (
    <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2.5" data-testid="devig-section">
      <p className="mb-1.5 text-[10px] font-medium uppercase tracking-widest text-slate-500">
        Shin devig (fair prob)
      </p>
      {devig == null ? (
        <p className="text-xs text-slate-600">Devig not computed -- no quotes.</p>
      ) : (
        <div className="flex items-center gap-4 font-mono text-xs">
          <span className="text-slate-400">
            fair prob: <span className="text-slate-100">{fmtPct(devig.fair_prob)}</span>
          </span>
          <span className="text-slate-400">
            vig: <span className="text-amber-400">{fmtPct(devig.vig_pct)}</span>
          </span>
          <span className="ml-auto text-[10px] text-slate-600">prob ratio -- no $</span>
        </div>
      )}
    </div>
  );
}

function TrailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800/60 py-1.5 last:border-0">
      <span className="text-[11px] uppercase tracking-wide text-slate-500">{label}</span>
      <span>{children}</span>
    </div>
  );
}

function DecisionTrail({
  decision, stakeUnits, tier, modelProb, clvStatus, decisionNote,
}: Pick<ExecutionTrailProps, "decision" | "stakeUnits" | "tier" | "modelProb" | "clvStatus" | "decisionNote">) {
  const isNoBet = !decision || decision === "no_bet";
  return (
    <div className="mt-3" data-testid="decision-trail">
      <p className="mb-1.5 text-[10px] font-medium uppercase tracking-widest text-slate-500">
        Decision trail
      </p>
      <div className="space-y-1.5">
        <TrailRow label="model prob">
          <span className="font-mono text-xs text-slate-200" data-testid="model-prob">
            {modelProb != null ? fmtPct(modelProb) : EMPTY_CELL}
          </span>
        </TrailRow>
        <TrailRow label="tier">
          <span data-testid="tier-badge">
            {tier ? (
              <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase", tierBadgeClass(tier))}>
                {tier}
              </span>
            ) : (
              <span className="font-mono text-xs text-slate-600">{EMPTY_CELL}</span>
            )}
          </span>
        </TrailRow>
        <TrailRow label="decision">
          <span data-testid="decision-label">
            <Badge tone={isNoBet ? "slate" : "green"}>{decision ?? "no_bet"}</Badge>
          </span>
        </TrailRow>
        <TrailRow label="stake (units, no $)">
          <span className="font-mono text-xs text-slate-200" data-testid="stake-units">
            {isNoBet ? <span className="text-slate-600">no_bet</span> : fmtUnits(stakeUnits)}
          </span>
        </TrailRow>
        <TrailRow label="CLV status">
          <span className="font-mono text-[11px]" data-testid="clv-status">
            {clvStatus === "INSUFFICIENT_DATA" || clvStatus == null ? (
              <span className="text-amber-600">INSUFFICIENT_DATA</span>
            ) : (
              <span className="text-slate-400">{clvStatus}</span>
            )}
          </span>
        </TrailRow>
      </div>
      {decisionNote ? (
        <p className="mt-2 text-[11px] leading-relaxed text-slate-500" data-testid="decision-note">
          {decisionNote}
        </p>
      ) : null}
    </div>
  );
}

function RealMoneyDenyNote() {
  return (
    <div
      className="mt-4 rounded-lg border border-red-900/30 bg-red-950/10 px-3 py-2"
      data-testid="real-money-deny"
      role="note"
      aria-label="real-money-deny"
    >
      <p className="text-[11px] leading-relaxed text-red-400/80">
        REAL-MONEY DENY: This system does not place real-money bets. Stakes are
        in units (no $ column). Execution is paper-only. CLV is the honest
        calibration yardstick; it may be INSUFFICIENT_DATA when no closing
        line was captured. No edge is claimed.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function ExecutionTrail({
  bookLines, bestBook, devig, decision, stakeUnits, tier, clvStatus,
  modelProb, decisionNote, loading, error, className,
}: ExecutionTrailProps) {
  if (loading) {
    return (
      <Panel title="Execution trail" className={className}>
        <p className="text-sm text-slate-500">checking...</p>
      </Panel>
    );
  }
  if (error) {
    return (
      <Panel title="Execution trail" className={className}>
        <Unavailable reason={error} />
        <RealMoneyDenyNote />
      </Panel>
    );
  }

  const trailProps = { decision, stakeUnits, tier, modelProb, clvStatus, decisionNote };
  const headerRight = (
    <span className="font-mono text-[10px] text-slate-500">units only -- no $</span>
  );

  if (!bookLines || bookLines.length === 0) {
    return (
      <Panel title="Execution trail" right={headerRight} className={className}>
        <Unavailable reason="No book lines available for this market." />
        <DecisionTrail {...trailProps} />
        <RealMoneyDenyNote />
      </Panel>
    );
  }

  return (
    <Panel title="Execution trail" right={headerRight} className={className}>
      <section aria-label="book lines">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-widest text-slate-500">
          Line shopping (decimal odds -- not a $ payout)
        </p>
        <BookLinesTable bookLines={bookLines} bestBook={bestBook} />
        <p className="mt-1 text-[10px] text-slate-600">
          Green = best line (highest decimal odds = lowest vig) at last capture.
        </p>
      </section>
      <DevigSection devig={devig} />
      <DecisionTrail {...trailProps} />
      <RealMoneyDenyNote />
    </Panel>
  );
}
