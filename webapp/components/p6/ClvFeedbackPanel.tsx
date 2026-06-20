"use client";

import { useCallback } from "react";
import {
  api,
  isUnavailable,
  type QuantClv,
  type ImproveTimeline,
} from "@/lib/p5api";
import { useLiveData } from "@/lib/useLiveData";
import { Panel, Unavailable, Badge, ModeDot, TickingFreshnessBadge } from "./Primitives";
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

  // Build asOf from ageSec so TickingFreshnessBadge can tick without re-fetching.
  const clvAsOf =
    clvAgeSec !== null
      ? new Date(Date.now() - clvAgeSec * 1000).toISOString()
      : null;

  return (
    <Panel
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
    >
      {/* Always-on honest framing line. Never 'profiting'/'shipping'. */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
        CLV (better-number-than-close) is a DO-NO-HARM yardstick, NEVER a
        profit/ROI target. vs_close stays UNPROVEN until gate-proven against a
        TRUE close. The self-improve loop is{" "}
        <span className="text-slate-300">
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
        <p className="mt-3 text-sm text-slate-500">loading...</p>
      ) : !clv || !summary || summary.n_bets === 0 ? (
        <p className="mt-3 text-xs text-slate-500">
          No graded-vs-close bets yet -- nothing to score. (An empty, honest
          ledger, not a 0% beat.)
        </p>
      ) : (
        <>
          {/* Headline verdict: beat / match / behind, in probability space. */}
          <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
            <div className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                mean CLV
              </span>
              <span
                className={cn(
                  "font-mono text-lg",
                  clvTone(mean) === "green"
                    ? "text-tier-a"
                    : clvTone(mean) === "amber"
                      ? "text-amber-400"
                      : "text-slate-300",
                )}
              >
                {mean === null
                  ? "--"
                  : `${mean >= 0 ? "+" : ""}${mean.toFixed(2)}%`}
              </span>
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
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                vs_close
              </span>
              <Badge tone={summary.vs_close_proven ? "green" : "amber"}>
                {summary.vs_close_proven ? "proven" : "UNPROVEN"}
              </Badge>
              {summary.clv_is_proxy ? (
                <span className="ml-1 font-mono text-[9px] text-amber-600/80">
                  proxy close
                </span>
              ) : null}
            </div>
          </div>

          {/* Per-sport CLV-over-cohort breakdown (probability space; no $). */}
          <SportBreakdown bySport={summary.by_sport} />

          {summary.note ? (
            <p className="mt-3 text-[11px] text-slate-600">{summary.note}</p>
          ) : null}
        </>
      )}

      {clv?.honest_note ? (
        <p className="mt-3 text-[11px] text-slate-600">{clv.honest_note}</p>
      ) : null}
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <span className="font-mono text-sm text-slate-200">{value}</span>
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
    <div className="mt-4">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        CLV vs close by sport (probability space)
      </div>
      <table className="mt-2 w-full text-xs">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
            <th className="pb-1 font-medium">Sport</th>
            <th className="pb-1 font-medium">n</th>
            <th className="pb-1 font-medium">mean CLV</th>
            <th className="pb-1 font-medium">beat close</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {entries.map(([sport, v]) => {
            const tone = clvTone(v.mean_clv_pct);
            return (
              <tr key={sport} className="text-slate-300">
                <td className="py-1.5 font-mono text-[10px] uppercase text-slate-200">
                  {sport}
                </td>
                <td className="py-1.5 font-mono text-[10px]">{v.n}</td>
                <td
                  className={cn(
                    "py-1.5 font-mono text-[10px]",
                    tone === "green"
                      ? "text-tier-a"
                      : tone === "amber"
                        ? "text-amber-400"
                        : "text-slate-400",
                  )}
                >
                  {v.mean_clv_pct === null
                    ? "--"
                    : `${v.mean_clv_pct >= 0 ? "+" : ""}${v.mean_clv_pct.toFixed(2)}%`}
                </td>
                <td className="py-1.5 font-mono text-[10px] text-slate-400">
                  {v.pct_beat_close === null
                    ? "--"
                    : `${(v.pct_beat_close * 100).toFixed(0)}%`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
