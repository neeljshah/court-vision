"use client";

import { useCallback } from "react";
import {
  api,
  type OpsStatus,
  type OpsService,
  type AutonomyStatus,
} from "@/lib/p5api";
import { Panel, Unavailable, Badge, ModeDot, timeAgoIso } from "./Primitives";
import { Num, Dot } from "@/components/ui/terminal";
import { useLiveData } from "@/lib/useLiveData";
import { cn } from "@/lib/utils";

// asOfStamp -- HH:MM:SS from an ISO/epoch-seconds timestamp. Never fabricated:
// callers only pass a real feed generated_at.
function asOfStamp(iso: string | number | null | undefined): string | null {
  if (iso == null) return null;
  const t = typeof iso === "number" ? iso * 1000 : Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleTimeString("en-US", { hour12: false });
}

// Shimmer placeholder while opsStatus resolves. Neutral: no green/red.
function ServiceTableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div
      role="status"
      aria-label="loading system health"
      aria-busy="true"
      data-testid="ops-service-skeleton"
    >
      <div className="mb-2 flex gap-3 pb-2">
        <div className="skeleton-shimmer h-2.5 w-14 opacity-40" />
        <div className="skeleton-shimmer h-2.5 w-8 opacity-40" />
        <div className="skeleton-shimmer h-2.5 w-20 opacity-40" />
        <div className="skeleton-shimmer h-2.5 w-14 opacity-40" />
      </div>
      <div className="space-y-2">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="flex items-center gap-3 py-1">
            <div className={cn("skeleton-shimmer h-2.5 opacity-30", i % 2 === 0 ? "w-24" : "w-20")} />
            <div className="skeleton-shimmer h-2.5 w-6 opacity-30" />
            <div className="skeleton-shimmer h-2.5 w-16 opacity-30" />
            <div className="skeleton-shimmer h-2.5 w-12 opacity-30" />
          </div>
        ))}
      </div>
      <div className="mt-3 skeleton-shimmer h-2 w-32 opacity-20" />
    </div>
  );
}

const SEV: Record<string, number> = { ok: 0, degraded: 1, down: 2 };
const sev = (s?: string | null) => (s ? (SEV[s] ?? 2) : 2);

function overallTone(o?: string): "green" | "amber" | "red" {
  return o === "ok" ? "green" : o === "degraded" ? "amber" : "red";
}

// Returns the more conservative (worst) of two overall strings.
function conservative(ops?: string, aut?: string | null): string {
  return sev(ops) >= sev(aut) ? (ops ?? "down") : (aut ?? "down");
}

// Shown only when the two feeds disagree within a poll window.
function ReconciliationNote() {
  return (
    <div
      role="note"
      aria-label="ops-reconciliation-note"
      className="mt-3 flex items-start gap-2 border border-amber-900/50 bg-amber-950/20 px-3 py-2 text-[11px] text-amber-400/90"
    >
      <span className="mt-0.5 shrink-0 font-mono text-amber-500">!</span>
      <span>
        ops feeds momentarily disagree &mdash; showing the more conservative
        state
      </span>
    </div>
  );
}

// OpsPanel: merges ops/status + ops/autonomy; header shows conservative (worst) state.
// Both feeds are managed by useLiveData in the same component so reconciliation
// is synchronous within a single render pass (no render-time side-effect patterns).
export function OpsPanel() {
  const opsFetcher = useCallback((signal: AbortSignal) => api.opsStatus(signal), []);
  const autFetcher = useCallback((signal: AbortSignal) => api.getAutonomyStatus(signal), []);

  const {
    data: opsData,
    isLoading: opsLoading,
    isStale: opsStale,
    error: opsErr,
  } = useLiveData<OpsStatus>(opsFetcher, { intervalMs: 15_000, staleAfterSec: 30 });

  const {
    data: autData,
    isLoading: autLoading,
    isStale: autStale,
    error: autErr,
  } = useLiveData<AutonomyStatus>(autFetcher, { intervalMs: 15_000, staleAfterSec: 30 });

  const opsOverall = opsData?.overall;
  const autOverall = autData?.overall ?? null;
  const opsLoaded = opsData != null || opsErr != null;
  const autLoaded = autData != null || autErr != null;

  // Hold both feeds: no green until both settle (avoids premature green flash).
  // While loading show 'checking' (slate); on isStale with last-good show amber.
  const combined: string | null =
    opsLoaded && autLoaded
      ? conservative(opsOverall, autOverall)
      : opsLoaded && opsOverall && opsOverall !== "ok"
        ? opsOverall
        : null;

  const feedsDisagree =
    autLoaded && opsData != null && opsOverall != null && autOverall !== opsOverall;

  // Either feed going stale must downgrade an otherwise-green overall: a
  // persistently-returned-but-stale doc cannot read green.
  const anyStale = opsStale || autStale;

  // Header badge: 'checking' before first load, 'stale' (amber) on poll staleness.
  function headerBadge() {
    if ((!opsLoaded || !autLoaded) && !combined) return <Badge tone="slate">checking</Badge>;
    if (opsStale && !opsData) return <Badge tone="amber">stale</Badge>;
    if (combined) {
      const tone = overallTone(combined);
      // Stale-green guard: show amber 'stale' instead of a stale green overall.
      if (anyStale && tone === "green") return <Badge tone="amber">stale</Badge>;
      return <Badge tone={tone}>{combined}</Badge>;
    }
    return <Badge tone="slate">checking</Badge>;
  }

  const panelAsOf =
    asOfStamp(opsData?.generated_at) ?? asOfStamp(autData?.generated_at ?? null);

  return (
    <Panel
      title="System health + freshness"
      asOf={panelAsOf}
      stale={anyStale}
      right={
        <span className="flex items-center gap-2">
          <span data-testid="ops-panel-overall">
            {headerBadge()}
          </span>
          <ModeDot mode="poll" />
        </span>
      }
    >
      {opsErr && !opsData ? (
        <Unavailable reason={opsErr} />
      ) : (opsLoading && !opsData) ? (
        <ServiceTableSkeleton />
      ) : opsData ? (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs" aria-label="service health status">
              <thead>
                <tr className="border-b border-border text-left">
                  <th scope="col" className="microlabel py-1.5 px-3">Service</th>
                  <th scope="col" className="microlabel py-1.5 px-3 text-center">Live</th>
                  <th scope="col" className="microlabel py-1.5 px-3">Last update</th>
                  <th scope="col" className="microlabel py-1.5 px-3">Breaker</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {opsData.services.map((svc) => <ServiceRow key={svc.name} svc={svc} />)}
              </tbody>
            </table>
          </div>
          {opsData.generated_at ? (
            <p className="mt-2 font-mono text-[10px] text-faint">
              status snapshot: {timeAgoIso(opsData.generated_at)}
            </p>
          ) : null}
          {opsData.notes && opsData.notes.length > 0 ? (
            <ul className="mt-2 space-y-0.5">
              {opsData.notes.map((n, i) => (
                <li key={i} className="text-[11px] text-amber-500/80">{n}</li>
              ))}
            </ul>
          ) : null}
          {feedsDisagree ? <ReconciliationNote /> : null}
        </>
      ) : (
        <ServiceTableSkeleton />
      )}

      {/* Autonomy block -- inline (no sub-component) so reconciliation is synchronous */}
      <div className="mt-4 border-t border-slate-800 pt-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Autonomy status</span>
          {autData ? (
            autStale && overallTone(autData.overall) === "green" ? (
              <Badge tone="amber">stale</Badge>
            ) : (
              <Badge tone={overallTone(autData.overall)}>{autData.overall}</Badge>
            )
          ) : null}
        </div>
        {autErr || (!autLoading && !autData) ? (
          <Unavailable reason={autErr || "autonomy_status.json missing or stale"} />
        ) : autLoading && !autData ? (
          <div className="space-y-1.5">
            {[0, 1].map((i) => (
              <div key={i} className="h-2.5 w-full animate-pulse rounded bg-slate-800/60" />
            ))}
          </div>
        ) : autData ? (
          <dl className="space-y-1.5 text-xs">
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">loop liveness</dt>
              <dd>
                <Badge tone={overallTone(autData.loop?.liveness_severity)}>
                  {autData.loop?.liveness_severity || "unknown"}
                </Badge>
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">loop cycle</dt>
              <dd className="font-mono text-foreground">{autData.loop?.cycle ?? "--"}</dd>
            </div>
            {autData.idle_reason ? (
              <div className="border border-border bg-surface-1 px-2 py-1.5 text-[11px] text-amber-500/80">
                {autData.idle_reason}
              </div>
            ) : null}
            {autData.generated_at != null ? (
              <p className="font-mono text-[10px] text-faint">
                autonomy snapshot:{" "}
                {typeof autData.generated_at === "number"
                  ? timeAgoIso(new Date(autData.generated_at * 1000).toISOString())
                  : timeAgoIso(autData.generated_at)}
              </p>
            ) : null}
            {autData.notes && autData.notes.length > 0 ? (
              <ul className="space-y-0.5">
                {autData.notes.map((n, i) => (
                  <li key={i} className="text-[11px] text-amber-500/80">{n}</li>
                ))}
              </ul>
            ) : null}
          </dl>
        ) : null}
      </div>
    </Panel>
  );
}

// breakerLabel: "open"/"closed"/raw/"--". Text, not color-only.
function breakerLabel(raw?: string | null): string {
  if (!raw) return "--";
  const lc = raw.toLowerCase();
  return lc === "open" || lc === "closed" ? lc : raw;
}

function ServiceRow({ svc }: { svc: OpsService }) {
  // Color is supplemental only (WCAG 1.4.1); text carries state.
  const liveText = svc.live === true ? "yes" : svc.live === false ? "no" : "--";
  const liveState = svc.live === true ? "ok" : svc.live === false ? "bad" : "warn";
  const bLabel = breakerLabel(svc.breaker);
  const bState = svc.breaker?.toLowerCase() ?? null;
  const breakerState = !bState || bState === "closed" ? "ok" : bState === "open" ? "bad" : "warn";
  const ago = svc.last_seen ? timeAgoIso(svc.last_seen) : null;

  return (
    <tr className="text-foreground hover:bg-surface-2">
      <td className="py-1.5 px-3">
        <span className={cn("font-mono text-[11px]", svc.critical ? "font-semibold" : "")}>{svc.name}</span>
        {svc.critical ? <span className="ml-1 text-[9px] uppercase text-amber-600">crit</span> : null}
      </td>
      <td className="py-1.5 px-3 text-center" data-testid={`live-cell-${svc.name}`}>
        <span className="inline-flex items-center gap-1.5 font-mono text-[11px]" aria-label={`live: ${liveText}`}>
          <Dot state={liveState} />
          {liveText}
        </span>
      </td>
      <td className="py-1.5 px-3">
        <span className="font-mono text-[10px] text-faint">{ago || (svc.fresh ? svc.fresh : "--")}</span>
        {svc.age_sec != null ? (
          <Num className="ml-1 text-[10px] text-faint">({Math.round(svc.age_sec)}s)</Num>
        ) : null}
      </td>
      <td className="py-1.5 px-3" data-testid={`breaker-cell-${svc.name}`}>
        <span className="inline-flex items-center gap-1.5 font-mono text-[10px]" aria-label={`breaker: ${bLabel}`}>
          <Dot state={breakerState} />
          {bLabel}
        </span>
      </td>
    </tr>
  );
}
