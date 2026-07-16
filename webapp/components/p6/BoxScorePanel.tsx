"use client";

import { useCallback } from "react";
import { api, isUnavailable, type Boxscore } from "@/lib/api";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Unavailable } from "./Primitives";
import { Num } from "@/components/ui/terminal";

// BoxScorePanel -- live player box score (min/pts/reb/ast) for a single game,
// grouped by team. Reuses the existing GET /api/boxscore/{sport}/{game_id}
// endpoint (already typed + client-tested) -- no new data source.
//
// HONESTY RAILS: degrades to an explicit "no live box score" state when the
// game hasn't started / the feed has none yet (never a fabricated row). A
// failed poll retains the last-good table (useLiveData contract) -- never
// blanks to red. No $ anywhere.
export function BoxScorePanel({ sport, gameId }: { sport: string; gameId: string }) {
  const fetcher = useCallback(
    (signal: AbortSignal) => api.boxscore(sport, gameId, signal),
    [sport, gameId],
  );

  const { data, ageSec, isStale, error } = useLiveData<Boxscore>(fetcher, {
    intervalMs: 20_000,
    staleAfterSec: 90,
    cacheKey: `game:${sport}:${gameId}:boxscore`,
  });

  const asOf =
    ageSec != null ? new Date(Date.now() - ageSec * 1000).toLocaleTimeString() : null;

  if (data === null || isUnavailable(data) || (data.players ?? []).length === 0) {
    const reason =
      data && isUnavailable(data)
        ? (data as unknown as { reason?: string }).reason
        : data
          ? data.honest_note || data.reason || "no live box score yet"
          : error || "checking...";
    return (
      <Panel title="Box score" asOf={asOf} stale={isStale}>
        <Unavailable reason={reason} />
      </Panel>
    );
  }

  // Group players by team, preserving first-seen team order (home/away order
  // as the feed returns it -- never re-sorted/invented).
  const byTeam = new Map<string, typeof data.players>();
  for (const p of data.players) {
    const arr = byTeam.get(p.team) ?? [];
    arr.push(p);
    byTeam.set(p.team, arr);
  }

  return (
    <Panel title="Box score" asOf={asOf} stale={isStale}>
      <div className="flex flex-col gap-3">
        {[...byTeam.entries()].map(([team, players]) => (
          <div key={team}>
            <div className="mb-1 font-data text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              {team}
            </div>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="microlabel py-1 pr-2">Player</th>
                  <th className="microlabel py-1 px-1 text-right">Min</th>
                  <th className="microlabel py-1 px-1 text-right">Pts</th>
                  <th className="microlabel py-1 px-1 text-right">Reb</th>
                  <th className="microlabel py-1 px-1 text-right">Ast</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {players.map((p, i) => (
                  <tr key={`${p.player}-${i}`}>
                    <td className="py-1 pr-2 truncate">{p.player}</td>
                    <td className="py-1 px-1 text-right"><Num>{p.min ?? "--"}</Num></td>
                    <td className="py-1 px-1 text-right"><Num>{p.pts ?? "--"}</Num></td>
                    <td className="py-1 px-1 text-right"><Num>{p.reb ?? "--"}</Num></td>
                    <td className="py-1 px-1 text-right"><Num>{p.ast ?? "--"}</Num></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
      {error ? (
        <p className="mt-2 font-data text-[10px] text-faint">
          feed error -- last-good box score shown ({error})
        </p>
      ) : null}
    </Panel>
  );
}
