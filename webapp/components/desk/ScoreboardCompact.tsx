// ScoreboardCompact.tsx -- the sealed in-game scoreboard folded to one row per
// (sport, arm) behind a disclosure, under one summary row per sport. Every cell is
// kept, INSUFFICIENT included; arms with no ticks fold under their own <details>.
// Server component, no client JS. PAPER ONLY: arm A is the venue mid, not a model.

import type { Desk, ScoreRow } from "@/lib/desk.server";
import { fmt } from "@/lib/desk.server";
import { T } from "./DeskShell";
import { FIGURES } from "@/lib/figures";

const FLOOR = FIGURES.forward_cell_floor_games.value;
const MID_NOTE = "arm A scored against its own mid price, so Brier 0.0000 by construction; not a result";

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

/** One summary row per sport: the cell holding the most games, with that cell's verdict. */
export function sportSummary(groups: ArmGroup[]): { sport: string; games: number; verdict: string }[] {
  const m = new Map<string, { games: number; verdict: string }>();
  for (const g of groups) for (const r of g.rows) {
    const games = r.n_games ?? 0;
    if (!m.has(g.sport) || games > m.get(g.sport)!.games) m.set(g.sport, { games, verdict: r.verdict ?? "no verdict" });
  }
  return [...m.entries()].map(([sport, v]) => ({ sport, ...v }));
}

const verdictText = (v: Record<string, number>) => Object.entries(v).map(([k, n]) => `${k} ${n}`).join(", ");

function ArmRows({ groups, arms }: { groups: ArmGroup[]; arms: Record<string, string> | null }) {
  return (
    <>
      <thead>
        <tr className="whitespace-nowrap border-b border-border text-left text-faint">
          {["sport", "arm", "cells", "cells with ticks", "most games in a cell", "verdicts", "detail"].map((h) =>
            <th key={h} className="px-3 py-1 font-normal">{h}</th>)}
        </tr>
      </thead>
      <tbody>
        {groups.map((g) => (
          <tr key={`${g.sport}-${g.arm}`} className="border-b border-border/50 align-top">
            <td className="px-3 py-1">{g.sport}</td>
            <td className="px-3 py-1" title={arms?.[g.arm] ?? undefined}>{g.arm}</td>
            <td className="px-3 py-1">{g.cells}</td>
            <td className="px-3 py-1">{g.scored}</td>
            <td className="px-3 py-1">{g.maxGames} of {FLOOR}</td>
            <td className="px-3 py-1">{verdictText(g.verdicts)}</td>
            <td className="px-3 py-1">
              <details>
                <summary className="cursor-pointer py-1 underline">show {g.cells} cells</summary>
                <T head={["segment", "target", "Brier", "log loss", "Brier minus A", "ticks", "games", "verdict", "reason"]}
                  rows={g.rows.map((r) => [r.segment, r.target, fmt(r.brier), fmt(r.logloss), fmt(r.brier_minus_A),
                    r.n_ticks ?? "-", r.n_games ?? "-", r.verdict ?? "-",
                    r.target === "mid" && r.arm === "A" && r.brier === 0 ? MID_NOTE : r.reason ?? ""])} />
              </details>
            </td>
          </tr>
        ))}
      </tbody>
    </>
  );
}

export function ScoreboardCompact({ sb, arms }: { sb: Sb; arms: Record<string, string> | null }) {
  const groups = groupScoreboard(sb);
  const live = groups.filter((g) => g.scored > 0);
  const empty = groups.filter((g) => g.scored === 0);
  return (
    <div className="flex flex-col gap-3 py-2">
      <ul className="px-3 font-data text-xs" data-testid="scoreboard-sport-summary">
        {sportSummary(groups).map((s) => (
          <li key={s.sport}>{s.games < FLOOR
            ? `${s.sport}: ${s.games} of ${FLOOR} games needed for a verdict; no verdict yet`
            : `${s.sport}: ${s.games} games; verdict ${s.verdict}`}</li>
        ))}
      </ul>
      <p className="px-3 text-xs text-muted-foreground" data-testid="scoreboard-mid-note">
        Rows with target=mid that print Brier 0.0000 are arm A scored against its own mid price: zero by
        construction, a plumbing check, not a result.
      </p>
      <details className="px-3 text-xs">
        <summary className="cursor-pointer py-1 underline">show the full cell grid ({sb.rows.length} cells)</summary>
        <p className="py-2 text-muted-foreground">
          Sealed pre-registration PREREG_2026-10-07. Each cell is one sport, segment, target and arm, scored on Brier
          and log loss; arm A is the venue YES mid (the reference), not a devigged price. A cell reads INSUFFICIENT
          until it holds {FLOOR} games. This export: {sb.games} games, {sb.ticks} ticks, {sb.rows.length} cells.
          Lower loss is better.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full font-data text-xs" data-testid="scoreboard-compact"><ArmRows groups={live} arms={arms} /></table>
        </div>
        {empty.length > 0 && (
          <details className="py-2" data-testid="scoreboard-empty-arms">
            <summary className="cursor-pointer py-1 underline">show {empty.length} empty arms</summary>
            <div className="overflow-x-auto">
              <table className="w-full font-data text-xs"><ArmRows groups={empty} arms={arms} /></table>
            </div>
          </details>
        )}
        {arms && (
          <dl className="grid gap-1 py-2 text-muted-foreground sm:grid-cols-2">
            {Object.entries(arms).map(([a, what]) => (
              <div key={a}><dt className="inline font-data text-foreground">arm {a}: </dt><dd className="inline">{what}</dd></div>
            ))}
          </dl>
        )}
      </details>
    </div>
  );
}
