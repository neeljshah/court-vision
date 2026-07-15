"use client";

import { useSnapshots } from "@/lib/store";
import { Activity } from "lucide-react";
import { Panel, Num } from "@/components/ui/terminal";

export function GameHeader() {
  const snaps = useSnapshots();
  const gameIds = Object.keys(snaps);
  const gid = gameIds[0];
  const snap = gid ? snaps[gid] : undefined;

  if (!snap) {
    return (
      <Panel className="p-5">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Activity className="h-4 w-4 animate-pulse" />
          <span className="text-sm">Waiting for the first snapshot...</span>
        </div>
      </Panel>
    );
  }

  const margin = (snap.home_score ?? 0) - (snap.away_score ?? 0);
  const arrow = margin > 0 ? "+" : margin < 0 ? "-" : "=";
  const arrowColour =
    margin > 0 ? "text-up" : margin < 0 ? "text-down" : "text-muted-foreground";

  return (
    <Panel className="p-5">
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-baseline gap-4 text-2xl font-semibold">
            <span>{snap.away_team || "AWAY"}</span>
            <Num className="text-muted-foreground">{snap.away_score ?? 0}</Num>
            <span className="px-2 text-muted-foreground">@</span>
            <span>{snap.home_team || "HOME"}</span>
            <Num className="text-foreground">{snap.home_score ?? 0}</Num>
            <Num className={`ml-3 ${arrowColour}`}>
              {arrow}{Math.abs(margin)}
            </Num>
          </div>
          <div className="mt-1 font-data text-sm text-muted-foreground">
            Q{snap.period ?? "-"} - {snap.clock ?? "--:--"} -{" "}
            <span className="microlabel">
              {snap.game_status || "?"}
            </span>
          </div>
        </div>
        <div className="font-data text-right text-xs text-faint">
          game {gid}
        </div>
      </div>
    </Panel>
  );
}
