"use client";

import { useCallback } from "react";
import { api, isUnavailable, type ClvScoreboard as Clv } from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { ClvScoreboard } from "./ClvScoreboard";
import { TickingFreshnessBadge, ModeDot } from "./Primitives";
import type { Unavailable } from "@/lib/types";

// ClvScoreboardLive -- fetches the portfolio-wide CLV scoreboard from
// /api/paper/clv and renders the (presentational) ClvScoreboard.
// Uses useLiveData: auto-refresh every 20 s, pause on hidden tab, last-updated
// age badge, failed poll keeps last-good data.
export function ClvScoreboardLive() {
  const fetcher = useCallback(
    (signal: AbortSignal) =>
      api.paperClv(signal).then((d) => {
        // Surface unavailable sentinel so useLiveData can handle it properly.
        if (isUnavailable(d)) return d as Unavailable;
        return d as Clv;
      }),
    [],
  );

  const { data, ageSec, isStale, error, isLoading } = useLiveData<Clv>(
    fetcher,
    { intervalMs: 20_000, staleAfterSec: 60 },
  );

  // Build an ISO string from ageSec so TickingFreshnessBadge can display it.
  // When we have no data yet and no last-update, pass null (unavailable state).
  const asOfIso =
    ageSec !== null
      ? new Date(Date.now() - ageSec * 1000).toISOString()
      : null;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wide text-slate-500">
          CLV scoreboard
        </span>
        <span className="flex items-center gap-2">
          {error || isStale ? (
            <span className="font-mono text-[10px] text-amber-400">
              {error ? "feed stale/error" : "stale"}
            </span>
          ) : null}
          <TickingFreshnessBadge asOf={asOfIso} />
          <ModeDot mode="poll" />
        </span>
      </div>
      {isLoading && !data ? (
        <p className="text-sm text-slate-500">loading...</p>
      ) : (
        <ClvScoreboard clv={data} />
      )}
    </div>
  );
}
