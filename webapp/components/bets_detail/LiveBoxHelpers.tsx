"use client";

// LiveBoxHelpers.tsx -- self-contained helpers for LiveBoxPanel.
// Extracted to keep LiveBoxPanel.tsx under the 300 LOC hard rail.
// No behaviour change: all exports are the same shapes/props as before.

import * as React from "react";
import { cn } from "@/lib/utils";
import { Num } from "@/components/ui/terminal";
import type { BoxscorePlayer } from "@/lib/p5api_ext";

// A payload older than this is considered stale even if HTTP returned 200.
// 3 minutes covers normal poll cadence (10s) with generous margin for slow
// daemons; anything beyond that is a dead/completed-game snapshot.
export const LIVE_STALE_MS = 3 * 60 * 1000;

/** Returns age in milliseconds from generated_at, or Infinity if absent/unparseable. */
export function ageMs(generatedAt: string | null | undefined): number {
  if (!generatedAt) return Infinity;
  const t = Date.parse(generatedAt);
  if (isNaN(t)) return Infinity;
  return Date.now() - t;
}

/** Format a duration in ms as a human-readable "Xm Ys ago" string. */
export function fmtAge(ms: number): string {
  if (ms === Infinity || ms < 0) return "unknown";
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  if (m > 0) return `${m}m ${s}s ago`;
  return `${s}s ago`;
}

export const fmtStat = (v: number | null | undefined): string =>
  v == null ? "--" : String(v);

export const fmtMin = (v: number | null | undefined): string => {
  if (v == null) return "--";
  const m = Math.floor(v);
  const s = Math.round((v - m) * 60);
  return s > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${m}`;
};

/** Format an ISO feed timestamp as HH:MM:SS for a PanelHead as-of stamp. */
export function fmtClockIso(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleTimeString("en-US", { hour12: false });
}

// LiveBoxSkeleton -- shimmer for ingame=null (fetch in flight). Matches the live
// content shape: score-line + win-prob bar + boxscore rows. Never green/red.
const SK = "skeleton-shimmer";
export function LiveBoxSkeleton() {
  return (
    <div role="status" aria-label="Live game data loading" data-testid="live-box-skeleton" className="flex flex-col gap-4">
      {/* Score-line: away abbr | away score | @ | home score | home abbr | clock */}
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <div className={`${SK} h-4 w-10`} />
          <div className={`${SK} h-7 w-8`} />
          <span className="text-faint">@</span>
          <div className={`${SK} h-7 w-8`} />
          <div className={`${SK} h-4 w-10`} />
        </div>
        <div className={`${SK} h-4 w-16`} />
      </div>
      {/* Win-prob bar shimmer */}
      <div className="flex flex-col gap-1">
        <div className={`${SK} h-2 w-full`} />
        <div className={`${SK} h-3 w-2/3`} />
      </div>
      {/* Boxscore table shimmer: header row + 5 player rows */}
      <div className="flex flex-col gap-1" role="table" aria-label="Live boxscore loading">
        <div className="flex gap-2 pb-1">
          <div className={`${SK} h-3 flex-1`} />
          {[0,1,2,3].map((i) => <div key={i} className={`${SK} h-3 w-8`} />)}
        </div>
        {[0,1,2,3,4].map((n) => (
          <div key={n} className="flex gap-2 py-1 border-t border-border">
            <div className={`${SK} h-4 flex-1`} />
            {[0,1,2,3].map((i) => <div key={i} className={`${SK} h-4 w-8`} />)}
          </div>
        ))}
      </div>
      <span className="sr-only">Checking for live game data...</span>
    </div>
  );
}

export function ClvStatusChip({ status }: { status: string | null | undefined }) {
  if (!status) return null;
  const isInsufficient = status === "INSUFFICIENT_DATA";
  return (
    <span
      className={cn(
        "inline-block border px-1.5 py-0.5 font-data text-[10px]",
        isInsufficient
          ? "border-warning/40 text-stale"
          : status === "true_close"
          ? "border-success/40 text-up"
          : "border-border text-muted-foreground",
      )}
    >
      CLV: {status}
    </span>
  );
}

// AgeChip -- styled "last updated" chip shown in the live panel header.
// Only rendered when age is finite and the payload is fresh (not stale).
// Never green: uses neutral slate styling to avoid implying live/active state.
export function AgeChip({ ageLabel, generatedAt }: { ageLabel: string; generatedAt: string | null | undefined }) {
  return (
    <span
      data-testid="age-chip"
      title={`Feed generated_at: ${generatedAt ?? "unknown"}`}
      className={cn(
        "inline-flex items-center gap-1 border border-border",
        "bg-surface-2 px-1.5 py-0.5 font-data text-[10px] text-muted-foreground",
      )}
    >
      {/* Small dot indicating feed is being received (neutral, not green/live) */}
      <span className="h-1.5 w-1.5 rounded-full bg-faint" aria-hidden="true" />
      {ageLabel}
    </span>
  );
}

// StaleAgeNote -- shown inside the Stale state block with explicit human-readable age.
// Satisfies the "stale path renders explicit age" acceptance criterion.
export function StaleAgeNote({ age, generatedAt }: { age: number; generatedAt: string | null | undefined }) {
  const ageStr = age < Infinity ? fmtAge(age) : "unknown";
  return (
    <p
      data-testid="stale-age"
      className="mt-1.5 font-data text-[10px] text-stale"
    >
      Last update: {ageStr}
      {generatedAt && (
        <span className="ml-1 text-faint" title={generatedAt}>
          ({generatedAt})
        </span>
      )}
    </p>
  );
}

// BoxTable -- accessible boxscore table with proper caption, scope=col headers,
// and aria-label. Satisfies WCAG 1.3.1 (info and relationships).
export function BoxTable({ players }: { players: BoxscorePlayer[] }) {
  if (players.length === 0) return null;
  return (
    <table
      className="w-full text-xs"
      aria-label="Live player boxscore"
    >
      <caption className="sr-only">
        Live in-game player statistics -- points, rebounds, assists, and minutes played.
      </caption>
      <thead>
        <tr className="text-left">
          <th scope="col" className="microlabel pb-1.5 px-3">player</th>
          <th scope="col" className="microlabel pb-1.5 px-3 text-right">min</th>
          <th scope="col" className="microlabel pb-1.5 px-3 text-right">pts</th>
          <th scope="col" className="microlabel pb-1.5 px-3 text-right">reb</th>
          <th scope="col" className="microlabel pb-1.5 px-3 text-right">ast</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {players.map((p, i) => (
          <tr key={`${p.name}-${i}`} className="text-foreground hover:bg-surface-2">
            <td className="py-1.5 px-3 font-medium">
              {p.name}
              {p.team && (
                <span className="ml-1 font-data text-[10px] text-faint">
                  {p.team}
                </span>
              )}
            </td>
            <td className="py-1.5 px-3 text-right">
              <Num>{fmtMin(p.min)}</Num>
            </td>
            <td className="py-1.5 px-3 text-right">
              <Num>{fmtStat(p.pts)}</Num>
            </td>
            <td className="py-1.5 px-3 text-right">
              <Num>{fmtStat(p.reb)}</Num>
            </td>
            <td className="py-1.5 px-3 text-right">
              <Num>{fmtStat(p.ast)}</Num>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
