"use client";

import { useCallback } from "react";
import {
  api,
  isUnavailable,
  type QuantClv,
  type ImproveTimeline,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Unavailable, Badge, ModeDot, TickingFreshnessBadge } from "./Primitives";
import { Panel, PanelHead } from "@/components/ui/terminal";
import type { Unavailable as UnavailableType } from "@/lib/types";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

// CLV summary percentages arrive scaled (36.3 means 36.3%).

// ClvFeedbackPanel -- the execution-in-the-loop state, shown HONESTLY.
// Reads GET /api/quant/clv (the sign-audited beat-the-close CLV scoreboard,
// probability space) and GET /api/improve/timeline (the self-improve loop, which
// is MEASUREMENT-ONLY / INERT until a human enables it).
//
// HONESTY RAILS:
//   - CLV is "better-number-than-close", a DO-NO-HARM yardstick -- never a
//     profit/ROI target. vs_close is UNPROVEN by default.
//   - In-game CLV may be INSUFFICIENT_DATA (honest), never fabricated or greened.
//   - The loop is labelled "measurement-only -- loop not enabled" by default.
//   - A stale/absent CLV feed degrades to Unavailable -- NEVER green-on-missing.
//   - Failed polls keep last-good data (useLiveData contract); isStale/error surface.
//
// Composes terminal.tsx's Panel/PanelHead directly (rather than the Primitives
// Panel adapter) so the as-of stamp reflects the real CLV feed age.

export function ClvFeedbackPanel() {
  const clvFetcher = useCallback(
    (signal: AbortSignal) =>
      api.getQuantClv(signal).then((d) => {
        if (isUnavailable(d)) return d as UnavailableType;
        return d as QuantClv;
      }),
    [],
  );

  const timelineFetcher = useCallback(
    (signal: AbortSignal) =>
      api.getImproveTimeline(signal).then((d) => {
        if (isUnavailable(d)) return d as UnavailableType;
        return d as ImproveTimeline;
      }),
    [],
  );

  const {
    ageSec: clvAgeSec,
    isStale: clvStale,
    error: clvErr,
    isLoading: clvLoading,
  } = useLiveData<QuantClv>(clvFetcher, {
    intervalMs: 20_000,
    staleAfterSec: 60,
  });

  const { data: timeline } = useLiveData<ImproveTimeline>(timelineFetcher, {
    intervalMs: 30_000,
    staleAfterSec: 120,
  });

  // The loop is INERT until a human flips PIPELINE_ENABLED. Default to the honest
  // "not enabled" label whenever the timeline says enabled !== true.
  const loopEnabled = timeline?.enabled === true;


  // Build asOf from ageSec so PanelHead's as-of stamp reflects the real feed age.
  const clvAsOf =
    clvAgeSec !== null
      ? new Date(Date.now() - clvAgeSec * 1000).toISOString()
      : null;

  return (
    <Panel>
      <PanelHead
        title="execution-in-the-loop -- CLV feedback (measurement-only)"
        right={
          <span className="flex items-center gap-2">
            {loopEnabled ? (
              <Badge tone="amber">enabled - gated</Badge>
            ) : (
              <Badge tone="slate">measurement-only - loop not enabled</Badge>
            )}
            <TickingFreshnessBadge asOf={clvAsOf} />
            <ModeDot mode="poll" />
          </span>
        }
      />
      <div className="p-4">
        {/* Always-on honest framing line. Never 'profiting'/'shipping'. */}
        <div className="border border-border bg-surface-1 px-3 py-2 text-xs leading-relaxed text-faint">
          CLV (better-number-than-close) is a DO-NO-HARM yardstick, NEVER a
          profit/ROI target. vs_close stays UNPROVEN until gate-proven against a
          TRUE close. The self-improve loop is{" "}
          <span className="text-muted-foreground">
            {loopEnabled
              ? "enabled by a human gate (still gate-disciplined; no $ claimed)"
              : "measurement-only and NOT enabled -- it ships nothing"}
          </span>
          .
        </div>

        {/* Stale/error banner -- never hidden, never green-on-missing. */}
        {(clvStale || clvErr) && !clvLoading ? (
          <div className="mt-2">
            <Unavailable
              reason={
                clvErr
                  ? `CLV feed stale/absent -- ${clvErr}`
                  : "CLV feed stale -- last-good data shown below"
              }
            />
          </div>
        ) : null}

        <div className="mt-3" data-testid="clv-feedback-unavailable">
          <Unavailable reason={CLV_UNAVAILABLE} />
        </div>
      </div>
    </Panel>
  );
}
