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
import { Num, Dot } from "@/components/ui/terminal";

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
      <p className="py-2 text-xs text-faint" data-testid="no-book-lines">
        No book quotes captured yet.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto" data-testid="book-lines-table">
      <table className="w-full text-xs" role="table">
        <thead>
          <tr className="border-b border-border">
            {["book", "decimal odds", "line", "best"].map((h) => (
              <th
                key={h}
                scope="col"
                className={cn(
                  "microlabel py-1.5",
                  h === "book" ? "pr-3 text-left" : "px-3 text-right",
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bookLines.map((bl, i) => {
            const isBest = !!bestBook && bl.book === bestBook;
            return (
              <tr
                key={`${bl.book}-${i}`}
                data-testid={isBest ? "best-line-row" : undefined}
                className="border-b border-border hover:bg-surface-2 last:border-0"
              >
                <td className="py-1.5 pr-3 font-data text-foreground">
                  {bl.book}
                  {bl.is_pm && (
                    <span className="ml-1 text-[9px] text-info">PM</span>
                  )}
                </td>
                <td
                  className="px-3 py-1.5 text-right"
                  title={bl.captured_at ? `captured ${bl.captured_at}` : undefined}
                >
                  <Num className={isBest ? "font-semibold text-emerald-400" : "text-foreground"}>
                    {fmt2(bl.decimal_odds)}
                    {fmtLine(bl.line)}
                  </Num>
                </td>
                <td className="px-3 py-1.5 text-right">
                  <Num className="text-faint">
                    {bl.line != null ? fmtLine(bl.line) : EMPTY_CELL}
                  </Num>
                </td>
                <td className="px-3 py-1.5 text-right font-data text-[10px]">
                  {isBest ? (
                    <span
                      data-testid="best-badge"
                      className="border border-border px-1 py-0.5 text-up"
                    >
                      best
                    </span>
                  ) : (
                    <span className="text-faint">{EMPTY_CELL}</span>
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
    <div className="mt-3 border border-border bg-surface-1 px-3 py-2.5" data-testid="devig-section">
      <p className="microlabel mb-1.5">Shin devig (fair prob)</p>
      {devig == null ? (
        <p className="text-xs text-faint">Devig not computed -- no quotes.</p>
      ) : (
        <div className="flex items-center gap-4 text-xs">
          <span className="text-muted-foreground">fair prob: <Num className="text-foreground">{fmtPct(devig.fair_prob)}</Num></span>
          <span className="text-muted-foreground">vig: <Num className="text-foreground">{fmtPct(devig.vig_pct)}</Num></span>
          <span className="ml-auto font-data text-[10px] text-faint">prob ratio -- no $</span>
        </div>
      )}
    </div>
  );
}

function TrailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-1.5 last:border-0">
      <span className="microlabel">{label}</span>
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
      <p className="microlabel mb-1.5 flex items-center gap-1.5">
        <Dot state={isNoBet ? "warn" : "ok"} />
        Decision trail
      </p>
      <div className="space-y-1.5">
        <TrailRow label="model prob">
          <span data-testid="model-prob">
            <Num className="text-foreground">{modelProb != null ? fmtPct(modelProb) : EMPTY_CELL}</Num>
          </span>
        </TrailRow>
        <TrailRow label="tier">
          <span data-testid="tier-badge">
            {tier ? (
              <span className={cn("inline-flex items-center border px-2 py-0.5 font-data text-[10px] uppercase", tierBadgeClass(tier))}>
                {tier}
              </span>
            ) : (
              <Num className="text-faint">{EMPTY_CELL}</Num>
            )}
          </span>
        </TrailRow>
        <TrailRow label="decision">
          <span data-testid="decision-label">
            <Badge tone={isNoBet ? "slate" : "green"}>{decision ?? "no_bet"}</Badge>
          </span>
        </TrailRow>
        <TrailRow label="stake (units, no $)">
          <span data-testid="stake-units">
            <Num className="text-foreground">{isNoBet ? <span className="text-faint">no_bet</span> : fmtUnits(stakeUnits)}</Num>
          </span>
        </TrailRow>
        <TrailRow label="CLV status">
          <span className="font-data text-[11px]" data-testid="clv-status">
            {clvStatus === "INSUFFICIENT_DATA" || clvStatus == null ? (
              <span className="text-amber-600">INSUFFICIENT_DATA</span>
            ) : (
              <span className="text-faint">{clvStatus}</span>
            )}
          </span>
        </TrailRow>
      </div>
      {decisionNote ? (
        <p className="mt-2 text-[11px] leading-relaxed text-faint" data-testid="decision-note">
          {decisionNote}
        </p>
      ) : null}
    </div>
  );
}

function RealMoneyDenyNote() {
  return (
    <div
      className="mt-4 border border-danger/40 bg-danger/10 px-3 py-2"
      data-testid="real-money-deny"
      role="note"
      aria-label="real-money-deny"
    >
      <p className="text-[11px] leading-relaxed text-danger">
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
        <p className="text-sm text-faint">checking...</p>
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
    <span className="font-data text-[10px] text-faint">units only -- no $</span>
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
        <p className="microlabel mb-1">
          Line shopping (decimal odds -- not a $ payout)
        </p>
        <BookLinesTable bookLines={bookLines} bestBook={bestBook} />
        <p className="mt-1 font-data text-[10px] text-faint">
          Best line (highest decimal odds = lowest vig) at last capture.
        </p>
      </section>
      <DevigSection devig={devig} />
      <DecisionTrail {...trailProps} />
      <RealMoneyDenyNote />
    </Panel>
  );
}
