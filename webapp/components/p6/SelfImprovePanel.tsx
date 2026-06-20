"use client";

import { useCallback } from "react";
import {
  api,
  type ImproveTimeline,
  type ImproveTimelineCycle,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Unavailable, Badge, ModeDot, timeAgoIso } from "./Primitives";

// SelfImprovePanel -- reads GET /api/improve/timeline and renders the self-improve
// loop state HONESTLY. The loop is MEASUREMENT-ONLY: until a human creates the
// PIPELINE_ENABLED sentinel it ships NOTHING. So when enabled=false we show a clear
// "Measurement-only - not enabled" badge -- NEVER "shipping"/"learning". We surface
// the cycle count, the last decision, n_promoted (0 here), and edge_claimed:false.
// No $ field is ever read or rendered.
//
// Live polling: uses useLiveData (pause-on-hidden, last-good, stale badge).
// No bespoke setInterval.

function decisionTone(
  decision: string | null | undefined,
): "green" | "amber" | "slate" {
  const d = (decision || "").toUpperCase();
  if (d === "SHIP" || d === "PROMOTE") return "green";
  if (d === "REJECT" || d === "NO_CANDIDATE" || d === "NO_NEW_GAMES")
    return "amber";
  return "slate";
}

function cycleTime(at: ImproveTimelineCycle["at"]): string | null {
  if (at == null) return null;
  if (typeof at === "number") {
    // Epoch seconds -> ISO so timeAgoIso can parse it.
    return timeAgoIso(new Date(at * 1000).toISOString());
  }
  return timeAgoIso(at);
}

export function SelfImprovePanel() {
  const fetcher = useCallback(
    (s: AbortSignal) => api.getImproveTimeline(s) as Promise<ImproveTimeline>,
    [],
  );
  const { data, error: err } = useLiveData<ImproveTimeline>(fetcher, {
    intervalMs: 10000,
    staleAfterSec: 60,
  });

  // The honest headline badge. enabled=false (this box) -> measurement-only; we
  // must NEVER label it 'shipping' or 'learning'. enabled=true would still only
  // mean a human turned the gate on -- the loop never flips it itself.
  const enabled = data?.enabled === true;
  const headBadge = !data ? null : enabled ? (
    <Badge tone="amber">enabled - gated</Badge>
  ) : (
    <Badge tone="slate">Measurement-only - not enabled</Badge>
  );

  const lastCycle =
    data && data.cycles.length > 0
      ? data.cycles[data.cycles.length - 1]
      : null;

  return (
    <Panel
      title="Self-improve loop"
      right={
        <span className="flex items-center gap-2">
          {headBadge}
          <ModeDot mode="poll" />
        </span>
      }
    >
      {err ? (
        <Unavailable reason={err} />
      ) : !data ? (
        <p className="text-sm text-slate-500">loading...</p>
      ) : (
        <>
          {/* Honest state line: never 'shipping'/'learning' when not enabled. */}
          <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
            {enabled
              ? "Loop ENABLED by a human gate. It still only ships when every eval gate passes; no $ edge is claimed."
              : "MEASUREMENT-ONLY: this loop reads INERT. It never creates the PIPELINE_ENABLED sentinel, ships nothing, and claims no edge. It beats a heartbeat but promotes nothing until a human enables it."}
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <div className="flex items-center justify-between">
              <dt className="text-slate-500">cycle count</dt>
              <dd className="font-mono text-slate-300">
                {data.cycle_counter ?? data.n_cycles ?? data.cycles.length}
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-slate-500">n_promoted</dt>
              <dd className="font-mono text-slate-300">{data.n_promoted}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-slate-500">edge_claimed</dt>
              <dd>
                <Badge tone={data.edge_claimed ? "red" : "green"}>
                  {data.edge_claimed ? "true" : "false"}
                </Badge>
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-slate-500">last decision</dt>
              <dd>
                {lastCycle ? (
                  <Badge tone={decisionTone(lastCycle.decision)}>
                    {lastCycle.decision || "none"}
                  </Badge>
                ) : (
                  <span className="font-mono text-slate-500">none</span>
                )}
              </dd>
            </div>
          </dl>

          {/* Per-cycle tail (the loop's OWN decisions; nothing fabricated). */}
          {data.cycles.length > 0 ? (
            <div className="mt-3">
              <div className="text-[10px] uppercase tracking-wide text-slate-500">
                Recent cycles
              </div>
              <ul className="mt-2 space-y-1">
                {data.cycles
                  .slice(-6)
                  .reverse()
                  .map((c) => (
                    <li
                      key={c.cycle}
                      className="flex items-center justify-between gap-2 font-mono text-[11px]"
                    >
                      <span className="flex items-center gap-2">
                        <span className="text-slate-600">#{c.cycle}</span>
                        <Badge tone={decisionTone(c.decision)}>
                          {c.decision || "?"}
                        </Badge>
                        {c.reason ? (
                          <span className="truncate text-slate-500">
                            {c.reason}
                          </span>
                        ) : null}
                      </span>
                      {cycleTime(c.at) ? (
                        <span className="shrink-0 text-slate-600">
                          {cycleTime(c.at)}
                        </span>
                      ) : null}
                    </li>
                  ))}
              </ul>
            </div>
          ) : (
            <p className="mt-3 text-[11px] text-slate-600">
              No cycles logged yet (cold / inert).
            </p>
          )}

          {data.honest_note ? (
            <p className="mt-3 text-[11px] text-slate-600">{data.honest_note}</p>
          ) : null}
        </>
      )}
    </Panel>
  );
}
