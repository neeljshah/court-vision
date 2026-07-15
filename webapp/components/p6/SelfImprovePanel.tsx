"use client";

import { useCallback } from "react";
import {
  api,
  type ImproveTimeline,
  type ImproveTimelineCycle,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Unavailable, Badge, ModeDot, timeAgoIso } from "./Primitives";
import { Num } from "@/components/ui/terminal";

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

// cycleStamp -- HH:MM:SS from the same at value, for the panel head. Never
// fabricated: null when the cycle has no timestamp.
function cycleStamp(at: ImproveTimelineCycle["at"]): string | null {
  if (at == null) return null;
  const t = typeof at === "number" ? at * 1000 : Date.parse(at);
  return Number.isNaN(t) ? null : new Date(t).toLocaleTimeString("en-US", { hour12: false });
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
      asOf={lastCycle ? cycleStamp(lastCycle.at) : null}
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
        <p className="text-sm text-muted-foreground">loading...</p>
      ) : (
        <>
          {/* Honest state line: never 'shipping'/'learning' when not enabled. */}
          <div className="border border-border bg-surface-1 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            {enabled
              ? "Loop ENABLED by a human gate. It still only ships when every eval gate passes; no $ edge is claimed."
              : "MEASUREMENT-ONLY: this loop reads INERT. It never creates the PIPELINE_ENABLED sentinel, ships nothing, and claims no edge. It beats a heartbeat but promotes nothing until a human enables it."}
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">cycle count</dt>
              <dd>
                <Num className="text-foreground">
                  {data.cycle_counter ?? data.n_cycles ?? data.cycles.length}
                </Num>
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">n_promoted</dt>
              <dd><Num className="text-foreground">{data.n_promoted}</Num></dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">edge_claimed</dt>
              <dd>
                <Badge tone={data.edge_claimed ? "red" : "green"}>
                  {data.edge_claimed ? "true" : "false"}
                </Badge>
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">last decision</dt>
              <dd>
                {lastCycle ? (
                  <Badge tone={decisionTone(lastCycle.decision)}>
                    {lastCycle.decision || "none"}
                  </Badge>
                ) : (
                  <span className="font-mono text-muted-foreground">none</span>
                )}
              </dd>
            </div>
          </dl>

          {/* Per-cycle tail (the loop's OWN decisions; nothing fabricated). */}
          {data.cycles.length > 0 ? (
            <div className="mt-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
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
                        <Num className="text-faint">#{c.cycle}</Num>
                        <Badge tone={decisionTone(c.decision)}>
                          {c.decision || "?"}
                        </Badge>
                        {c.reason ? (
                          <span className="truncate text-muted-foreground">
                            {c.reason}
                          </span>
                        ) : null}
                      </span>
                      {cycleTime(c.at) ? (
                        <span className="shrink-0 text-faint">
                          {cycleTime(c.at)}
                        </span>
                      ) : null}
                    </li>
                  ))}
              </ul>
            </div>
          ) : (
            <p className="mt-3 text-[11px] text-faint">
              No cycles logged yet (cold / inert).
            </p>
          )}

          {data.honest_note ? (
            <p className="mt-3 text-[11px] text-faint">{data.honest_note}</p>
          ) : null}
        </>
      )}
    </Panel>
  );
}
