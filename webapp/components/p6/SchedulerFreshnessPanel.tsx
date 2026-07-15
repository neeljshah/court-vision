"use client";

// SchedulerFreshnessPanel -- honest "is the producer/scheduler keeping each
// sport's snapshot fresh?" surface. Reads GET /api/produce/status (per-sport
// producer freshness) and renders the last-update age for EVERY registered
// sport.
//
// HARD RAILS:
//   * stale-never-green: age is re-derived locally from each sport's OWN
//     generated_at (and cross-checked against the backend age_seconds). A sport
//     whose snapshot age exceeds the SLA reads STALE (amber/red), never green --
//     even if the backend stamped status="ok".
//   * scheduler-gap honesty: if a registered sport is absent from the producer
//     status payload, it is shown explicitly as "not scheduled / no snapshot"
//     (slate, never green) rather than silently omitted -- so a scheduler that
//     drops a sport from its rotation is visible, not hidden.
//   * UNITS only; no $ field is ever rendered here.

import { useCallback } from "react";
import {
  api,
  SPORTS,
  type ProduceStatus,
  type ProduceSportStatus,
} from "@/lib/p5api";
import { Panel, Unavailable, Badge, timeAgoIso } from "./Primitives";
import { Num, Dot } from "@/components/ui/terminal";
import { useLiveData } from "@/lib/useLiveData";

// A producer snapshot older than this (by its OWN generated_at, or the backend
// age_seconds) is STALE -> never green. The producer cadence is sub-minute, so
// 10 min is a generous SLA before we stop calling a snapshot fresh.
const SLA_SEC = 10 * 60;

type Tone = "green" | "amber" | "red" | "slate";

// localAgeSec -- age derived from the feed's OWN generated_at, never the client
// fetch time. Falls back to the backend-reported age_seconds when no timestamp.
export function localAgeSec(s: ProduceSportStatus, now = Date.now()): number | null {
  if (s.generated_at) {
    const t = Date.parse(s.generated_at);
    if (!Number.isNaN(t)) return Math.max(0, (now - t) / 1000);
  }
  if (typeof s.age_seconds === "number" && Number.isFinite(s.age_seconds)) {
    return Math.max(0, s.age_seconds);
  }
  return null;
}

// rowTone -- stale-never-green. Green ONLY when the producer claims fresh AND the
// locally-derived age is within the SLA. Missing snapshot -> slate (neutral, not
// red). Aged-out snapshot -> amber (stale, never green). A hard producer error
// for that sport -> red.
export function rowTone(s: ProduceSportStatus): Tone {
  if (s.status === "missing" || (!s.generated_at && s.age_seconds == null)) {
    return "slate";
  }
  if (s.status === "error" || s.ok === false) {
    // ok=false with a known age is stale-amber; a genuine error string is red.
    if (s.status === "error") return "red";
  }
  const age = localAgeSec(s);
  if (age == null) return "slate";
  if (age > SLA_SEC) return "amber"; // aged out -> stale, never green
  return s.ok === true && s.status !== "stale" ? "green" : "amber";
}

function ageLabel(s: ProduceSportStatus): string {
  if (s.generated_at) return timeAgoIso(s.generated_at);
  const age = localAgeSec(s);
  if (age == null) return "no timestamp";
  return `${Math.round(age)}s ago`;
}

export function SchedulerFreshnessPanel() {
  const fetcher = useCallback(
    (signal: AbortSignal) => api.getProduceStatus(undefined, signal),
    [],
  );

  const { data, isLoading, isStale, error } = useLiveData<ProduceStatus>(
    fetcher,
    { intervalMs: 15_000, staleAfterSec: 30 },
  );

  // Merge the served sports with the full registered roster so a sport that the
  // scheduler dropped from its rotation is shown as a gap, not silently omitted.
  const served = new Map<string, ProduceSportStatus>(
    (data?.sports ?? []).map((s) => [s.sport, s]),
  );
  const rows: ProduceSportStatus[] = SPORTS.map(
    (sport) =>
      served.get(sport) ?? {
        sport,
        ok: false,
        status: "missing",
        generated_at: null,
        age_seconds: null,
        n_games: 0,
        n_markets: 0,
        reason: "not scheduled / no snapshot",
      },
  );

  const anyStale = rows.some((r) => {
    const t = rowTone(r);
    return t === "amber" || t === "red" || t === "slate";
  });

  // Panel-level asOf: the freshest per-sport generated_at across the roster,
  // formatted HH:MM:SS. Never fabricated -- null when no sport has a timestamp.
  const newestIso = rows
    .map((r) => r.generated_at)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(-1);
  const asOfStamp = (() => {
    if (!newestIso) return null;
    const t = Date.parse(newestIso);
    return Number.isNaN(t) ? null : new Date(t).toLocaleTimeString("en-US", { hour12: false });
  })();

  // Header badge: 'checking' before first load (neutral slate), amber if poll
  // went stale (isStale from useLiveData), else honest per-sport computation.
  function headerBadge() {
    if (isLoading && !data) return <Badge tone="slate">checking</Badge>;
    if (isStale && !data) return <Badge tone="amber">stale</Badge>;
    if (data) {
      return (
        <Badge tone={anyStale ? "amber" : "green"}>
          {anyStale ? "some sports stale" : "all fresh"}
        </Badge>
      );
    }
    return <Badge tone="slate">checking</Badge>;
  }

  return (
    <Panel
      title="Producer / scheduler freshness"
      asOf={asOfStamp}
      stale={anyStale}
      right={headerBadge()}
    >
      {error && !data ? (
        <Unavailable reason={error} />
      ) : isLoading && !data ? (
        <div
          role="status"
          aria-busy="true"
          aria-label="loading producer freshness"
          className="space-y-1.5"
        >
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-3 w-full animate-pulse rounded bg-slate-800/60" />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" aria-label="per-sport producer freshness">
            <thead>
              <tr className="border-b border-border text-left">
                <th scope="col" className="microlabel py-1.5 px-3">Sport</th>
                <th scope="col" className="microlabel py-1.5 px-3">Last update</th>
                <th scope="col" className="microlabel py-1.5 px-3 text-center">State</th>
                <th scope="col" className="microlabel py-1.5 px-3 text-right">Games</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((s) => {
                const tone = rowTone(s);
                const dotState = tone === "green" ? "ok" : tone === "red" ? "bad" : "warn";
                const stateText =
                  tone === "green"
                    ? "fresh"
                    : s.status === "missing"
                      ? "not scheduled"
                      : tone === "red"
                        ? "error"
                        : "STALE";
                return (
                  <tr key={s.sport} className="text-foreground hover:bg-surface-2" data-testid={`produce-row-${s.sport}`}>
                    <td className="py-1.5 px-3 font-mono text-[11px] uppercase">{s.sport}</td>
                    <td className="py-1.5 px-3 font-mono text-[10px] text-faint">
                      {ageLabel(s)}
                    </td>
                    <td className="py-1.5 px-3 text-center">
                      <span className="inline-flex items-center gap-1.5">
                        <Dot state={dotState} />
                        <Badge tone={tone}>{stateText}</Badge>
                      </span>
                    </td>
                    <td className="py-1.5 px-3 text-right">
                      <Num className="text-muted-foreground">{s.n_games ?? 0}</Num>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-[11px] text-faint">
        Last-update age is derived from each sport&apos;s own generated_at (stale
        never reads green). A sport missing from the producer rotation shows as
        &quot;not scheduled&quot; rather than being hidden. Units only; no $.
      </p>
    </Panel>
  );
}
