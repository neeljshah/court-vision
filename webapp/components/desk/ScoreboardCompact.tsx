// ScoreboardCompact.tsx -- the sealed in-game scoreboard folded to one row per
// (sport, arm). Every cell is kept, INSUFFICIENT included; the per-segment cells
// sit behind a native <details> expand control instead of a 200-row grid.
// Server component, no client JS. PAPER ONLY: arm A is the venue mid, not a model.

import type { Desk, ScoreRow } from "@/lib/desk.server";
import { fmt } from "@/lib/desk.server";
import { T } from "./DeskShell";

type Sb = NonNullable<Desk["scoreboard"]>;

export type ArmGroup = {
  sport: string; arm: string; cells: number; scored: number; maxGames: number;
  verdicts: Record<string, number>; rows: ScoreRow[];
};

/** Fold scoreboard rows to (sport, arm) groups in sport order, then the export's arm order. */
export function groupScoreboard(sb: Sb): ArmGroup[] {
  const order = sb.arm_order ?? [];
  const map = new Map<string, ArmGroup>();
  for (const r of sb.rows) {
    const k = `${r.sport}|${r.arm}`;
    const g = map.get(k) ?? { sport: r.sport, arm: r.arm, cells: 0, scored: 0, maxGames: 0, verdicts: {}, rows: [] };
    g.cells += 1;
    if ((r.n_ticks ?? 0) > 0) g.scored += 1;
    g.maxGames = Math.max(g.maxGames, r.n_games ?? 0);
    const v = r.verdict ?? "no verdict";
    g.verdicts[v] = (g.verdicts[v] ?? 0) + 1;
    g.rows.push(r);
    map.set(k, g);
  }
  const rank = (a: string) => (order.indexOf(a) === -1 ? order.length : order.indexOf(a));
  return [...map.values()].sort((a, b) => a.sport.localeCompare(b.sport) || rank(a.arm) - rank(b.arm) || a.arm.localeCompare(b.arm));
}

const verdictText = (v: Record<string, number>) => Object.entries(v).map(([k, n]) => `${k} ${n}`).join(", ");

export function ScoreboardCompact({ sb, arms }: { sb: Sb; arms: Record<string, string> | null }) {
  const groups = groupScoreboard(sb);
  return (
    <div className="flex flex-col gap-3 py-2">
      <p className="px-3 text-xs text-muted-foreground">
        Sealed pre-registration PREREG_2026-10-07. Each cell is one sport, segment, target and arm, scored on Brier
        and log loss; arm A is the venue YES mid (the reference), not a devigged price. A cell reads INSUFFICIENT
        until it holds 30 games. This export: {sb.games} games, {sb.ticks} ticks, {sb.rows.length} cells. Lower
        loss is better.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full font-data text-xs" data-testid="scoreboard-compact">
          <thead>
            <tr className="whitespace-nowrap border-b border-border text-left text-faint">
              {["sport", "arm", "cells", "cells with ticks", "most games in a cell", "verdicts", "cells"].map((h, i) =>
                <th key={i} className="px-3 py-1 font-normal">{i === 6 ? "detail" : h}</th>)}
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={`${g.sport}-${g.arm}`} className="border-b border-border/50 align-top">
                <td className="px-3 py-1">{g.sport}</td>
                <td className="px-3 py-1" title={arms?.[g.arm] ?? undefined}>{g.arm}</td>
                <td className="px-3 py-1">{g.cells}</td>
                <td className="px-3 py-1">{g.scored}</td>
                <td className="px-3 py-1">{g.maxGames} of 30</td>
                <td className="px-3 py-1">{verdictText(g.verdicts)}</td>
                <td className="px-3 py-1">
                  <details>
                    <summary className="cursor-pointer py-1 underline">show {g.cells} cells</summary>
                    <T head={["segment", "target", "Brier", "log loss", "Brier minus A", "ticks", "games", "verdict", "reason"]}
                      rows={g.rows.map((r) => [r.segment, r.target, fmt(r.brier), fmt(r.logloss), fmt(r.brier_minus_A),
                        r.n_ticks ?? "-", r.n_games ?? "-", r.verdict ?? "-", r.reason ?? ""])} />
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {arms && (
        <dl className="grid gap-1 px-3 text-xs text-muted-foreground sm:grid-cols-2">
          {Object.entries(arms).map(([a, what]) => (
            <div key={a}><dt className="inline font-data text-foreground">arm {a}: </dt><dd className="inline">{what}</dd></div>
          ))}
        </dl>
      )}
    </div>
  );
}
