"use client";

// InGameNumber -- the per-game calibrated in-game win-prob (the PROVEN measured
// calibration edge), from GET /api/ingame/{sport}/{game_id}. Polls every 15s via
// the canonical useLiveData hook (pauses when tab hidden, retains last-good on a
// failed poll, shows stale badge + updated age -- never crashes the page).
//
// HONESTY RAILS: this is a CALIBRATION number, not a market edge. vs_close is
// always shown UNPROVEN (we never claim a beat). When there is no live state we
// fall back to the pregame prior p0 and say so; an endpoint error degrades to an
// honest stale display (last-good retained), never a red-failed blank. NO $ anywhere.
// stale-never-green: the live pulse / green badge is shown ONLY when fresh.

import { useCallback } from "react";
import { useLiveData } from "@/lib/useLiveData";
import { api, isUnavailable, type InGameServed } from "@/lib/api";
import { LiveBadge } from "@/components/live/LiveBadge";
import { fmtPct } from "@/lib/utils";
import type { Unavailable } from "@/lib/types";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";

export function InGameNumber({
  sport,
  gameId,
}: {
  sport: string;
  gameId: string;
}) {
  // Stable fetcher -- memoised on sport/gameId so useLiveData does not re-register
  // the interval on unrelated re-renders.
  const fetcher = useCallback(
    (signal: AbortSignal): Promise<InGameServed | Unavailable> =>
      api.ingame(sport, gameId, signal) as Promise<InGameServed | Unavailable>,
    [sport, gameId],
  );

  const {
    data,
    ageSec,
    isStale,
    error,
    isLoading,
  } = useLiveData<InGameServed>(fetcher, {
    intervalMs: 15_000,
    staleAfterSec: 45,
    timeoutMs: 8_000,
    cacheKey: `game:${sport}:${gameId}:ingame`,
  });

  // On the very first load (no data yet, no prior good state) show neutral "checking".
  if (isLoading && data === null) {
    return (
      <Panel>
        <PanelHead title="In-game number (calibration)" />
        <div className="flex items-center justify-between p-3">
          <p className="font-data text-xs text-faint">checking...</p>
          <LiveBadge ageSec={null} isStale={false} error={null} isLoading />
        </div>
      </Panel>
    );
  }

  // Failed poll with NO prior good state: the endpoint has never succeeded.
  // Show honest Unavailable with neutral amber (not red), still no $ anywhere.
  if (data === null && error) {
    return (
      <Panel>
        <PanelHead title="In-game number (calibration)" />
        <div className="flex items-center justify-between p-3">
          <p className="text-xs text-stale">{error}</p>
          <LiveBadge ageSec={null} isStale={false} error={error} isLoading={false} />
        </div>
      </Panel>
    );
  }

  // We have data (possibly stale). The isUnavailable check applies to the INITIAL
  // response -- once useLiveData has good data, it retains it across failed polls.
  // A runtime unavailable sentinel from the API means the game is not servable now.
  const apiUnavailable = data !== null && isUnavailable(data);
  if (apiUnavailable) {
    const reason = (data as unknown as Unavailable).reason ?? "no in-game number";
    return (
      <Panel>
        <PanelHead title="In-game number (calibration)" />
        <div className="flex items-center justify-between p-3">
          <p className="text-xs text-stale">{reason}</p>
          <LiveBadge ageSec={ageSec} isStale={isStale} error={error} isLoading={false} />
        </div>
      </Panel>
    );
  }

  // Good data (fresh or stale -- useLiveData retains last-good on a failed poll).
  const live = data?.live_state ?? null;
  const served = data?.served ?? null;
  const pWin = served?.p_win ?? data?.p0 ?? null;
  // stale-never-green: a completed game (status matches final/post/complete OR
  // frac_elapsed >= 1.0) must NOT be labelled "live P(home win)".
  const done = /final|post|complete/i.test(live?.status ?? "");
  const isLive =
    !!live && live.state_diff != null && !done && (live.frac_elapsed ?? 0) < 1;
  const provenance = served?.provenance ?? [];

  return (
    <Panel>
      <PanelHead
        title="In-game number (calibration)"
        right={
          <span className="border border-warning px-1.5 py-px font-data text-[10px] font-bold uppercase tracking-wider text-warning">
            vs close UNPROVEN
          </span>
        }
      />

      <div className="p-3">
        {/* Freshness badge: stale-never-green; shows "updated Ns ago" when fresh */}
        <div className="mb-2 flex justify-end">
          <LiveBadge
            ageSec={ageSec}
            isStale={isStale}
            error={error}
            isLoading={false}
          />
        </div>

        <div className="flex items-baseline justify-between">
          <span className="microlabel">
            {isLive ? "live P(home win)" : done ? "final number" : "pregame prior p0"}
          </span>
          <span data-testid="ingame-pwin">
            <Num className="text-lg text-foreground">
              {pWin != null ? fmtPct(pWin, false) : "--"}
            </Num>
          </span>
        </div>

        {live ? (
          <div className="mt-2 font-data text-[11px] text-faint">
            {(live.home || live.home_abbr || "HOME")} vs{" "}
            {(live.away || live.away_abbr || "AWAY")}
            {live.status ? ` - ${live.status}` : ""}
            {live.frac_elapsed != null
              ? ` - ${(live.frac_elapsed * 100).toFixed(0)}% elapsed`
              : ""}
          </div>
        ) : (
          <p className="mt-2 font-data text-[11px] text-faint">
            no live state -- showing the pregame prior, not a live number.
          </p>
        )}

        {provenance.length ? (
          <details className="mt-3 font-data text-[11px] text-faint">
            <summary className="cursor-pointer select-none">provenance</summary>
            <ul className="mt-1 space-y-0.5">
              {provenance.map((p, i) => (
                <li key={`${p}-${i}`}>{p}</li>
              ))}
            </ul>
          </details>
        ) : null}

        <p className="mt-3 border-t border-border pt-2 font-data text-[10px] leading-relaxed text-faint">
          Calibration, not a market edge. The in-game prior-conditioning is the
          proven MEASURED calibration improvement. No $ claimed.
        </p>
      </div>
    </Panel>
  );
}
