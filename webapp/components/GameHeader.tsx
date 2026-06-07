"use client";

import { useSnapshots } from "@/lib/store";
import { Activity } from "lucide-react";

export function GameHeader() {
  const snaps = useSnapshots();
  const gameIds = Object.keys(snaps);
  const gid = gameIds[0];
  const snap = gid ? snaps[gid] : undefined;

  if (!snap) {
    return (
      <header className="rounded-xl border border-slate-800 bg-bg-panel p-5">
        <div className="flex items-center gap-3 text-slate-400">
          <Activity className="h-4 w-4 animate-pulse" />
          <span className="text-sm">Waiting for the first snapshot…</span>
        </div>
      </header>
    );
  }

  const margin = (snap.home_score ?? 0) - (snap.away_score ?? 0);
  const arrow = margin > 0 ? "▲" : margin < 0 ? "▼" : "▬";
  const arrowColour =
    margin > 0 ? "text-tier-a" : margin < 0 ? "text-red-400" : "text-slate-400";

  return (
    <header className="rounded-xl border border-slate-800 bg-bg-panel p-5">
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-baseline gap-4 text-2xl tabular font-semibold">
            <span>{snap.away_team || "AWAY"}</span>
            <span className="text-slate-500">{snap.away_score ?? 0}</span>
            <span className="text-slate-500 px-2">@</span>
            <span>{snap.home_team || "HOME"}</span>
            <span className="text-slate-300">{snap.home_score ?? 0}</span>
            <span className={`ml-3 ${arrowColour}`}>
              {arrow} {Math.abs(margin)}
            </span>
          </div>
          <div className="mt-1 text-sm text-slate-400 tabular">
            Q{snap.period ?? "-"} · {snap.clock ?? "--:--"} ·{" "}
            <span className="uppercase tracking-wide text-xs text-slate-500">
              {snap.game_status || "?"}
            </span>
          </div>
        </div>
        <div className="text-right text-xs text-slate-500 font-mono">
          game {gid}
        </div>
      </div>
    </header>
  );
}
