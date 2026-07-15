"use client";

// LiveIndicator -- the prominent, honest "is the stack RUNNING INDEPENDENTLY?"
// banner + the supervisor process roster. It reads the REAL supervisor doc via
// the same-origin read-only route GET /api/ops/supervisor (which enforces a
// stale SLA before this component ever sees it).
//
// HARD RAIL -- stale-never-green: the green "LIVE - RUNNING INDEPENDENTLY" badge
// is shown ONLY when `live === true`, which the route sets ONLY when the feed is
// FRESH (updated_at within SLA) AND all_ready AND no proc is DEGRADED/DOWN. A
// missing / stale / degraded feed degrades to IDLE / DEGRADED honestly, with the
// explicit reason and NO fabricated uptime. The honest badges (self-improve
// READY-but-INERT, real-money DENY, in-game CLV INSUFFICIENT_DATA) are static
// rails -- they never claim an edge. NO $ field anywhere; UNITS only.
//
// Polling: uses the canonical useLiveData hook (not a bare tick setInterval):
//   - polls /api/ops/supervisor every 15 s
//   - pauses when document.hidden (visibilitychange); resumes + refetches on focus
//   - never throws; a failed poll retains last-good data and sets isStale/error
//   - shows neutral "checking" badge before first data (isLoading)
//   - isStale (after 60 s without a fresh poll) -- never green when stale
//   - shows last-updated age via TickingFreshnessBadge (stale-never-green)

import { useCallback } from "react";
import { useLiveData } from "@/lib/useLiveData";
import { fetchHonest } from "@/lib/fetchHonest";
import type { SupervisorStatus } from "@/lib/p5api";
import { isUnavailable } from "@/lib/p5api";
import { Panel, Unavailable, Badge, TickingFreshnessBadge } from "@/components/p6/Primitives";
import { cn } from "@/lib/utils";

function fmtDuration(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return "--";
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

// The ONE green-condition gate, mirrored from the route for the headline copy.
// We trust `live` (the route already required freshness+all_ready+no-degraded),
// but we re-state WHY so the badge text can never drift from the reason.
function headline(d: SupervisorStatus): {
  tone: "green" | "amber" | "red";
  label: string;
  sub: string;
} {
  if (d.live === true) {
    return {
      tone: "green",
      label: "LIVE - RUNNING INDEPENDENTLY",
      sub: "supervisor fresh - all services ready - self-healing (no human in the loop)",
    };
  }
  if (d.any_degraded) {
    return {
      tone: "red",
      label: "DEGRADED",
      sub: d.reason || "one or more supervised services is down or stale",
    };
  }
  return {
    tone: "amber",
    label: "IDLE / DEGRADED",
    sub: d.reason || "supervisor feed missing, stale, or not all-ready",
  };
}

// ---------------------------------------------------------------------------
// Supervisor fetcher -- same-origin Next.js route (NOT the P5 backend).
// Wrapped in useCallback so useLiveData gets a stable fetcher reference.
// ---------------------------------------------------------------------------

function supervisorFetcher(signal: AbortSignal) {
  return fetchHonest<SupervisorStatus>("/api/ops/supervisor", { signal });
}

export function LiveIndicator() {
  // useLiveData replaces the bare tick+setInterval pattern:
  //   - polls every 15 s (fast enough for a live-status panel)
  //   - pauses polling while document.hidden; resumes + refetches on focus
  //   - never crashes; a failed poll retains last-good data + sets isStale/error
  //   - isLoading=true only before the first successful poll (neutral "checking")
  //   - isStale flips true 60 s after the last successful poll
  const stableFetcher = useCallback(supervisorFetcher, []);
  const { data: rawData, isLoading, isStale, error, lastUpdatedAt } = useLiveData<
    SupervisorStatus
  >(stableFetcher, {
    intervalMs: 15_000,
    staleAfterSec: 60,
  });

  // When data arrives as an unavailable sentinel (e.g. 503 from the route),
  // useLiveData retains last-good and sets error. We never render stale as green.
  // If rawData is somehow an unavailable sentinel shape, treat it as null.
  const data: SupervisorStatus | null =
    rawData && !isUnavailable(rawData) ? rawData : null;

  // Derive the reason string from the live error or the data doc.
  const reason = error ?? (data == null ? "supervisor feed unavailable" : null);

  // Derive asOf from lastUpdatedAt for the ticking freshness badge.
  const asOf = lastUpdatedAt ? new Date(lastUpdatedAt).toISOString() : null;

  // isLoading is true while we've never had a successful poll AND no error yet.
  // Once an error arrives (unavailable sentinel), we stop showing "checking"
  // and immediately show IDLE / DEGRADED -- the feed is provably unavailable.
  const showLoading = isLoading && error === null;

  const h = data ? headline(data) : null;

  // Stale-never-green: if we have data but isStale, downgrade the tone.
  // The banner can only be green when live:true AND NOT stale.
  const effectiveTone: "green" | "amber" | "red" | null =
    h == null
      ? null
      : isStale && h.tone === "green"
        ? "amber"
        : h.tone;

  return (
    <Panel
      title="autonomous stack -- live status"
      right={
        showLoading ? (
          // Neutral "checking" -- never fabricate a status before first poll.
          <Badge tone="slate">checking</Badge>
        ) : isStale && h?.tone === "green" ? (
          // Stale-never-green: had a live feed but it aged out.
          <Badge tone="amber">stale</Badge>
        ) : h ? (
          <Badge tone={h.tone}>{h.tone === "green" ? "live" : h.tone}</Badge>
        ) : (
          <Badge tone="amber">idle</Badge>
        )
      }
    >
      {/* Prominent headline. Green ONLY on a fresh+all_ready+no-degraded feed.
          aria-live="polite" + aria-atomic="true": screen readers announce the full
          block as a unit whenever the status changes (polite = waits for idle;
          atomic = reads the whole region, not just the changed node).
          tabIndex={0} on the headline span makes the copy keyboard-discoverable
          so users can tab to it and have the label read aloud, not just rely on
          color to perceive the live/idle state. */}
      <div
        className={cn(
          "rounded-lg border px-4 py-3",
          effectiveTone === "green"
            ? "border-tier-a/40 bg-tier-a/10"
            : effectiveTone === "red"
              ? "border-red-900/50 bg-red-950/30"
              : "border-amber-900/50 bg-amber-950/20",
        )}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        aria-label={showLoading ? "checking" : (h?.label || "IDLE / DEGRADED")}
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={cn(
              "h-2.5 w-2.5 rounded-full",
              effectiveTone === "green"
                ? "bg-tier-a animate-pulse"
                : effectiveTone === "red"
                  ? "bg-red-500"
                  : "bg-amber-400",
            )}
          />
          {/* tabIndex={0} makes the headline copy keyboard-focusable so keyboard
              users can navigate to it and have the label read by AT, rather than
              having to infer state from the decorative dot color alone. */}
          <span
            tabIndex={0}
            className={cn(
              "font-mono text-sm font-semibold uppercase tracking-wide",
              effectiveTone === "green"
                ? "text-tier-a"
                : effectiveTone === "red"
                  ? "text-red-400"
                  : "text-amber-400",
            )}
          >
            {showLoading ? "checking..." : (h?.label || "IDLE / DEGRADED")}
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {showLoading
            ? "polling supervisor feed..."
            : h?.sub || reason || "supervisor_status.json missing or stale"}
        </p>
        {data ? (
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-muted-foreground">
            <span>
              uptime <span className="text-foreground">{fmtDuration(data.uptime_sec)}</span>
            </span>
            <span>
              services{" "}
              <span className="text-foreground">
                {data.all_ready ? "all ready" : "not all ready"}
              </span>
            </span>
            <span>
              self-heals{" "}
              <span className="text-foreground">{data.restarts_total} restarts</span>
            </span>
            <span>
              feed age{" "}
              <span className="text-foreground">{fmtDuration(data.age_sec)}</span>
            </span>
          </dl>
        ) : null}
      </div>

      {/* Honest, static rails -- these never claim an edge. */}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
        <Badge tone="amber">self-improve: READY-but-INERT (human-gated)</Badge>
        <Badge tone="red">real-money: DENY</Badge>
        <Badge tone="slate">in-game CLV: INSUFFICIENT_DATA (accruing)</Badge>
        <span className="font-mono text-[10px] text-faint">
          calibration not edge - vs_close UNPROVEN - units only, no $
        </span>
      </div>

      {/* Last-updated freshness badge -- stale-never-green via TickingFreshnessBadge. */}
      {asOf ? (
        <div className="mt-2">
          <TickingFreshnessBadge asOf={asOf} source="supervisor" />
        </div>
      ) : null}

      {/* Supervised process roster -- self-heal counts + heartbeat ages. */}
      {data && data.procs.length > 0 ? (
        <table
          className="mt-3 w-full text-xs"
          aria-label="Supervised process roster"
        >
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="pb-2 font-medium">Service</th>
              <th scope="col" className="pb-2 font-medium text-center">State</th>
              <th scope="col" className="pb-2 font-medium text-right">Heartbeat</th>
              <th scope="col" className="pb-2 font-medium text-right">Restarts</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {data.procs.map((p) => (
              <tr key={p.name} className="text-foreground">
                <td className="py-1.5 font-mono text-[11px]">{p.name}</td>
                <td className="py-1.5 text-center">
                  <span
                    className={cn(
                      "font-mono text-[10px]",
                      p.degraded ? "text-red-400" : "text-tier-a",
                    )}
                  >
                    {p.degraded ? "DEGRADED" : p.state}
                  </span>
                </td>
                <td className="py-1.5 text-right font-mono text-[10px] text-muted-foreground">
                  {p.heartbeat_age_sec != null
                    ? `${Math.round(p.heartbeat_age_sec)}s`
                    : "--"}
                </td>
                <td
                  className={cn(
                    "py-1.5 text-right font-mono text-[10px]",
                    p.restarts > 0 ? "text-amber-400" : "text-muted-foreground",
                  )}
                >
                  {p.restarts}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : !data ? (
        <div className="mt-3">
          <Unavailable reason={reason || "supervisor_status.json missing or stale"} />
        </div>
      ) : null}
    </Panel>
  );
}
