"use client";

import { useCallback } from "react";
import {
  api,
  isUnavailable,
  SPORTS,
  type ReportList,
  type InGameServed,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Unavailable, Badge, ModeDot, TickingFreshnessBadge } from "./Primitives";
import { fmtPct } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { Unavailable as UnavailableType } from "@/lib/types";

// InGamePanel -- per-game calibrated in-game P(home win) + provenance.
// For each sport, reads game_ids from /api/report/{sport} then fetches
// GET /api/ingame/{sport}/{game_id} for any games with a live_state.
// Shows: p_win (calibrated P(home win)), provenance lines joined.
//
// HONESTY RAILS:
//   - vs_close is UNPROVEN (no in-play odds available in offseason).
//   - CLV status INSUFFICIENT_DATA is rendered literally, never as 0 / green.
//   - A failed poll keeps last-good data (useLiveData contract).
//   - Offseason / no-live-games -> honest "no live games" (mechanism stays live).
//   - Degrades to p0 (pregame prior) when no live state; Unavailable on error.

type GameResult = {
  sport: string;
  game_id: string;
  data: InGameServed | null;
  err: string | null;
};

// Multi-sport composite fetcher: collects game_ids then fetches ingame data.
// Returns the array as a synthetic envelope so useLiveData handles it.
type InGameBundle = { results: GameResult[]; fetchedAt: number };

export function InGamePanel() {
  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<InGameBundle | UnavailableType> => {
      // Step 1: collect game_ids per sport (cap at 4 per sport).
      const gameRefs: { sport: string; game_id: string }[] = [];
      await Promise.all(
        SPORTS.map(async (sport) => {
          const d = await api.reportList(sport, signal);
          if (!isUnavailable(d) && (d as ReportList).game_ids) {
            (d as ReportList).game_ids.slice(0, 4).forEach((gid) =>
              gameRefs.push({ sport, game_id: gid }),
            );
          }
        }),
      );

      // Step 2: fetch ingame data for each game (cap at 12).
      const refs = gameRefs.slice(0, 12);
      const fetched: GameResult[] = await Promise.all(
        refs.map(async ({ sport, game_id }) => {
          try {
            const d = await api.ingame(sport, game_id, signal);
            if (isUnavailable(d)) {
              return {
                sport,
                game_id,
                data: null,
                err: (d as { reason?: string }).reason || "unavailable",
              };
            }
            return { sport, game_id, data: d as InGameServed, err: null };
          } catch (e) {
            return { sport, game_id, data: null, err: String(e) };
          }
        }),
      );

      // Return as a synthetic success (never throw -- caller decides stale/error).
      return { results: fetched, fetchedAt: Date.now() };
    },
    [],
  );

  const { data, ageSec, isStale, error, isLoading } =
    useLiveData<InGameBundle>(fetcher, {
      intervalMs: 15_000,
      staleAfterSec: 45,
    });

  const results = data?.results ?? [];
  const liveCount = results.filter((r) => r.data?.live_state).length;

  // Build asOf for the ticking badge from ageSec (no extra fetch).
  const asOf =
    ageSec !== null
      ? new Date(Date.now() - ageSec * 1000).toISOString()
      : null;

  return (
    <Panel
      title="In-game number (calibrated)"
      right={
        <span className="flex items-center gap-2">
          <Badge tone="slate">{liveCount} live</Badge>
          <TickingFreshnessBadge asOf={asOf} />
          <ModeDot mode="poll" />
        </span>
      }
    >
      {/* Stale/error banner -- never hidden. */}
      {(isStale || error) && data ? (
        <div className="mb-2">
          <Unavailable
            reason={
              error
                ? `feed error -- ${error}`
                : "feed stale -- last-good data shown"
            }
          />
        </div>
      ) : null}

      {isLoading && results.length === 0 ? (
        <p className="text-sm text-slate-500">loading...</p>
      ) : results.length === 0 ? (
        <p className="text-sm text-slate-500">No games on slate.</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
              <th className="pb-2 font-medium">Game</th>
              <th className="pb-2 font-medium text-right">P(home win)</th>
              <th className="pb-2 font-medium">State</th>
              <th className="pb-2 font-medium">Provenance / CLV</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {results.map((r) => (
              <GameRow key={`${r.sport}/${r.game_id}`} result={r} />
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-3 text-[11px] text-slate-600">
        CALIBRATION only. vs-close is UNPROVEN (no in-play odds available).
        p(home) = calibrated OOS probability; degrades to pregame prior when
        no live state. CLV may be INSUFFICIENT_DATA when no closing line exists.
      </p>
    </Panel>
  );
}

function GameRow({ result }: { result: GameResult }) {
  const { sport, game_id, data, err } = result;

  if (err) {
    return (
      <tr className="text-slate-500">
        <td className="py-1.5 font-mono text-[10px]">
          {sport}/{game_id}
        </td>
        <td colSpan={3} className="py-1.5 text-[10px] text-slate-600">
          {err.length > 60 ? err.slice(0, 60) + "..." : err}
        </td>
      </tr>
    );
  }
  if (!data) return null;

  const isLive = !!data.live_state;
  // BUG1 fix: backend returns p_win (not p_home).
  // LL-P0-04: on no_live_state the API still returns the pregame prior p0.
  const servedWin = data.served?.p_win;
  const priorP0 = data.p0 ?? data.live_state?.p0 ?? null;
  const pWin = servedWin ?? priorP0;
  const isPrior = servedWin == null && priorP0 != null;
  // BUG3 fix: provenance is string[] -- join for display.
  const provenanceRaw = data.served?.provenance;
  const provenance = Array.isArray(provenanceRaw)
    ? provenanceRaw.join(" | ")
    : (provenanceRaw || (isLive ? "base" : "pregame prior"));
  const model = data.served?.model;
  // BUG2 fix: backend live_state uses home/away (not home_abbr/away_abbr).
  const ls = data.live_state;
  const homeAbbr = ls?.home ?? ls?.home_abbr;
  const awayAbbr = ls?.away ?? ls?.away_abbr;
  const liveStatus = ls?.status;

  // CLV status from served field (may be INSUFFICIENT_DATA -- render honestly).
  const clvStatus = data.served?.vs_close ?? null;
  // INSUFFICIENT_DATA is a valid honest answer -- never fabricate / never green.
  const clvIsInsufficient =
    clvStatus === "INSUFFICIENT_DATA" || clvStatus === null;

  return (
    <tr className={cn("text-slate-300", isLive ? "text-slate-100" : "")}>
      <td className="py-1.5">
        <div className="font-mono text-[10px] text-slate-400">
          {sport}/{game_id}
        </div>
        {homeAbbr && awayAbbr ? (
          <div className="text-[11px]">
            {awayAbbr} @ {homeAbbr}
            {liveStatus ? (
              <span className="ml-1 text-slate-500">{liveStatus}</span>
            ) : null}
          </div>
        ) : null}
      </td>
      <td className="py-1.5 text-right font-mono tabular-nums text-sm">
        {pWin != null ? (
          <span
            className={cn(
              "font-semibold",
              pWin > 0.6
                ? "text-tier-a"
                : pWin < 0.4
                  ? "text-red-400"
                  : "text-slate-200",
              isPrior ? "opacity-80" : "",
            )}
            title={isPrior ? "pregame prior p0 (no live state)" : undefined}
          >
            {fmtPct(pWin)}
            {isPrior ? (
              <span className="ml-1 text-[9px] text-slate-500">p0</span>
            ) : null}
          </span>
        ) : (
          <span className="text-slate-600">unavailable</span>
        )}
      </td>
      <td className="py-1.5">
        <Badge tone={isLive ? "green" : "slate"}>
          {isLive ? "live" : "pregame"}
        </Badge>
      </td>
      <td className="py-1.5 font-mono text-[10px] text-slate-500">
        {provenance}
        {model ? (
          <span className="ml-1 text-slate-600">· {model}</span>
        ) : null}
        {/* CLV status -- INSUFFICIENT_DATA rendered literally, never as 0/green. */}
        {isLive ? (
          <span
            className={cn(
              "ml-1",
              clvIsInsufficient ? "text-slate-600" : "text-amber-600",
            )}
            data-testid="clv-status"
          >
            [vs-close:{" "}
            {clvIsInsufficient
              ? clvStatus === null
                ? "INSUFFICIENT_DATA"
                : clvStatus
              : clvStatus}
            ]
          </span>
        ) : null}
      </td>
    </tr>
  );
}
