"use client";

import { useSnapshots } from "@/lib/store";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

export function Lineups() {
  const snaps = useSnapshots();
  const gid = Object.keys(snaps)[0];
  const snap = gid ? snaps[gid] : undefined;
  const players = (snap?.players || []).filter((p) => (p.min ?? 0) > 0);
  players.sort((a, b) => (b.pts ?? 0) - (a.pts ?? 0));

  return (
    <Panel>
      <PanelHead title="On court" />
      <ul className="max-h-96 divide-y divide-border overflow-y-auto">
        {!players.length && (
          <li className="px-3 py-4 text-sm text-muted-foreground">No lineup yet...</li>
        )}
        {players.slice(0, 10).map((p) => (
          <li
            key={`${p.player_id}-${p.name}`}
            className="flex items-center gap-3 px-3 py-1.5 text-sm hover:bg-surface-2"
          >
            <div className="min-w-0 flex-1 truncate">
              <span className="text-foreground">{p.name}</span>{" "}
              <span className="text-xs text-muted-foreground">({p.team})</span>
            </div>
            <Num className="w-10 text-right text-muted-foreground">
              {Math.round(p.min ?? 0)}m
            </Num>
            <Num className="w-10 text-right text-foreground">
              {p.pts ?? 0}
            </Num>
            <Num
              className={`w-8 text-right ${
                (p.pf ?? 0) >= 4
                  ? "text-down"
                  : (p.pf ?? 0) >= 3
                  ? "text-stale"
                  : "text-muted-foreground"
              }`}
            >
              {p.pf ?? 0}f
            </Num>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
