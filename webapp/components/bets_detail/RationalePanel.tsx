"use client";

// RationalePanel.tsx -- model rationale using validated signals for a game.
//
// Shows which gate-tested signals feed this sport (ValidatedSignalsStrip
// read-only) plus a structured rationale drawn from the report's intel block.
// No fabricated signal values or edge claims -- only gate-tested verdicts.
//
// HONESTY RAILS: SHIP = calibration improvement (NEVER a $ edge). REJECT is
// a success. vs_close is UNPROVEN. No fabricated insight or number.

import * as React from "react";
import { Panel as TerminalPanel, PanelHead } from "@/components/ui/terminal";
import { SignalVerdictBadge } from "@/components/depth/SignalVerdictBadge";
import { ValidatedSignalsStrip } from "@/components/games_depth/ValidatedSignalsStrip";
import { Empty } from "@/components/honest/HonestState";
import type { Report } from "@/lib/types";

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

export interface RationalePanelProps {
  report: Report | null;
  sport: string;
  asOf?: string | null;
  stale?: boolean;
  className?: string;
}

// Extract a rationale block from the report's intel section (if present).
// We surface text-only keys -- never render a raw number as an edge claim.
interface RationaleBlock {
  key: string;
  label: string;
  body: string;
}

function extractRationale(report: Report | null): RationaleBlock[] {
  const intel = report?.intel;
  if (!intel || typeof intel !== "object") return [];
  const blocks: RationaleBlock[] = [];

  // note or narrative field
  const note = (intel as Record<string, unknown>).note;
  if (typeof note === "string" && note.trim().length > 0) {
    blocks.push({ key: "note", label: "model note", body: note });
  }

  // reasons array
  const reasons = (intel as Record<string, unknown>).reasons;
  if (Array.isArray(reasons)) {
    reasons.forEach((r, i) => {
      if (typeof r === "string") {
        blocks.push({ key: `reason-${i}`, label: "signal reason", body: r });
      }
    });
  }

  // pregame note
  const pgNote = report?.pregame?.note;
  if (typeof pgNote === "string" && pgNote.trim().length > 0) {
    blocks.push({ key: "pg-note", label: "pregame note", body: pgNote });
  }

  return blocks;
}

/** Validated signals + model rationale for a game (no $ -- calibration only). */
export function RationalePanel({ report, sport, asOf, stale = false, className }: RationalePanelProps) {
  const blocks = extractRationale(report);

  return (
    <Panel
      title="Rationale"
      asOf={asOf}
      stale={stale}
      right={
        <span className="font-data text-[10px] text-faint">
          calibration only -- no $
        </span>
      }
      className={className}
    >
      {/* Gate-tested signals for this sport (read-only reuse). */}
      <div className="mb-4">
        <p className="mb-1.5 microlabel">
          validated signals
        </p>
        <ValidatedSignalsStrip sport={sport} />
      </div>

      {/* Model notes / rationale from the intel block. */}
      <div>
        <p className="mb-1.5 microlabel">
          model notes
        </p>
        {blocks.length === 0 ? (
          <Empty
            label="No model notes"
            hint="No structured rationale available for this game yet."
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {blocks.map((b) => (
              <li
                key={b.key}
                className="border border-border bg-surface-1/30 px-3 py-2"
              >
                <span className="block microlabel">
                  {b.label}
                </span>
                <span className="block text-xs text-foreground">{b.body}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Honesty footer. */}
      <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-2">
        <SignalVerdictBadge verdict="SHIP" stat="calibration only" />
        <span className="self-center font-data text-[10px] text-faint">
          SHIP = calibration, not a market edge. vs-close UNPROVEN.
        </span>
      </div>
    </Panel>
  );
}
