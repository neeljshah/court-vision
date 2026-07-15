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
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { cn } from "@/lib/utils";
import type { Unavailable as UnavailableType } from "@/lib/types";

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

function clvTone(pct: number | null): "green" | "amber" | "slate" {
  if (pct === null) return "slate";
  if (pct > 0.05) return "green";
  if (pct < -0.05) return "amber";
  return "slate";
}

// Bucket the mean CLV into a beat / match / behind verdict (probability space).
function clvVerdict(pct: number | null): {
  label: string;
  tone: "green" | "amber" | "slate";
} {
  if (pct === null) return { label: "no graded close", tone: "slate" };
  if (pct > 0.1) return { label: "beating the close", tone: "green" };
  if (pct < -0.1) return { label: "behind the close", tone: "amber" };
  return { label: "matching the close", tone: "slate" };
}

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
    data: clv,
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

  const summary = clv?.clv;
  const mean = summary?.mean_clv_pct ?? null;
  const verdict = clvVerdict(mean);

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
        <div className="border border-border bg-surface-1 px-3 py-2 text-[11px] leading-relaxed text-faint">
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

        {clvLoading && !clv ? (
          <p className="mt-3 text-sm text-faint">loading...</p>
        ) : !clv || !summary || summary.n_bets === 0 ? (
          <p className="mt-3 text-xs text-faint">
            No graded-vs-close bets yet -- nothing to score. (An empty, honest
            ledger, not a 0% beat.)
          </p>
        ) : (
          <>
            {/* Headline verdict: beat / match / behind, in probability space. */}
            <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
              <div className="flex items-baseline gap-2">
                <span className="microlabel">mean CLV</span>
                <Num
                  className={cn(
                    "text-lg",
                    clvTone(mean) === "green"
                      ? "text-up"
                      : clvTone(mean) === "amber"
                        ? "text-stale"
                        : "text-muted-foreground",
                  )}
                >
                  {mean === null
                    ? "--"
                    : `${mean >= 0 ? "+" : ""}${mean.toFixed(2)}%`}
                </Num>
                <Badge tone={verdict.tone}>{verdict.label}</Badge>
              </div>
              <Stat
                label="beat close"
                value={
                  summary.pct_beat_close === null
                    ? "--"
                    : `${(summary.pct_beat_close * 100).toFixed(0)}%`
                }
              />
              <Stat label="graded bets" value={String(summary.n_bets)} />
              <div className="flex items-baseline gap-1">
                <span className="microlabel">vs_close</span>
                <Badge tone={summary.vs_close_proven ? "green" : "amber"}>
                  {summary.vs_close_proven ? "proven" : "UNPROVEN"}
                </Badge>
                {summary.clv_is_proxy ? (
                  <span className="ml-1 font-data text-[9px] text-stale">
                    proxy close
                  </span>
                ) : null}
              </div>
            </div>

            {/* Per-sport CLV-over-cohort breakdown (probability space; no $). */}
            <SportBreakdown bySport={summary.by_sport} />

            {summary.note ? (
              <p className="mt-3 text-[11px] text-faint">{summary.note}</p>
            ) : null}
          </>
        )}

        {clv?.honest_note ? (
          <p className="mt-3 text-[11px] text-faint">{clv.honest_note}</p>
        ) : null}
      </div>
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className="microlabel">{label}</span>
      <Num className="text-sm">{value}</Num>
    </span>
  );
}

function SportBreakdown({
  bySport,
}: {
  bySport: QuantClv["clv"]["by_sport"];
}) {
  const entries = Object.entries(bySport || {}).filter(
    ([, v]) => v && v.n > 0,
  );
  if (entries.length === 0) return null;
  return (
    <div className="mt-4 overflow-x-auto">
      <div className="microlabel">CLV vs close by sport (probability space)</div>
      <table className="mt-2 w-full text-xs">
        <thead>
          <tr className="microlabel text-left">
            <th className="px-3 py-1.5 font-medium">Sport</th>
            <th className="px-3 py-1.5 font-medium text-right">n</th>
            <th className="px-3 py-1.5 font-medium text-right">mean CLV</th>
            <th className="px-3 py-1.5 font-medium text-right">beat close</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {entries.map(([sport, v]) => {
            const tone = clvTone(v.mean_clv_pct);
            return (
              <tr key={sport} className="hover:bg-surface-2">
                <td className="px-3 py-1.5 font-data text-[10px] uppercase text-muted-foreground">
                  {sport}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <Num className="text-[10px]">{v.n}</Num>
                </td>
                <td className="px-3 py-1.5 text-right">
                  <Num
                    className={cn(
                      "text-[10px]",
                      tone === "green"
                        ? "text-up"
                        : tone === "amber"
                          ? "text-stale"
                          : "text-faint",
                    )}
                  >
                    {v.mean_clv_pct === null
                      ? "--"
                      : `${v.mean_clv_pct >= 0 ? "+" : ""}${v.mean_clv_pct.toFixed(2)}%`}
                  </Num>
                </td>
                <td className="px-3 py-1.5 text-right">
                  <Num className="text-[10px] text-faint">
                    {v.pct_beat_close === null
                      ? "--"
                      : `${(v.pct_beat_close * 100).toFixed(0)}%`}
                  </Num>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
