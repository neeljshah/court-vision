"use client";

import type { ClvScoreboard as Clv, ClvBySport } from "@/lib/p5api";
import { isUnavailable } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
import { fmtPct } from "@/lib/utils";

// ClvScoreboard -- the beat-the-close yardstick. CLV (better-number-than-close)
// is the only honest edge metric surfaced. No $ / ROI. Proxy closes flagged.
export function ClvScoreboard({ clv }: { clv: Clv | null | undefined }) {
  if (!clv || isUnavailable(clv)) {
    return (
      <Panel title="CLV scoreboard (beat the close)">
        <Unavailable reason={(clv as { reason?: string })?.reason} />
      </Panel>
    );
  }
  const settled = clv.n_bets > 0;
  return (
    <Panel
      title="CLV scoreboard (beat the close)"
      right={
        clv.clv_is_proxy ? <Badge tone="amber">proxy close</Badge> : null
      }
    >
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Graded bets" value={settled ? String(clv.n_bets) : "0"} />
        <Stat
          label="% beat close"
          value={
            clv.pct_beat_close != null ? fmtPct(clv.pct_beat_close, false) : "--"
          }
        />
        <Stat
          label="Mean CLV"
          value={clv.mean_clv_pct != null ? fmtPct(clv.mean_clv_pct) : "--"}
        />
      </div>
      {/* PT-P0-07: per-sport CLV breakdown -- a positive aggregate (e.g. NBA)
          must not mask a negative sport (e.g. soccer). Render each sport's own
          n / mean CLV / %-beat-close so the blend is honest. */}
      {settled ? <BySportBreakdown bySport={clv.by_sport} /> : null}
      {!settled ? (
        <p className="mt-3 text-xs text-slate-500">
          No settled bets yet -- CLV populates as paper bets grade against the
          close. No $ edge is claimed.
        </p>
      ) : null}
    </Panel>
  );
}

function BySportBreakdown({
  bySport,
}: {
  bySport: Record<string, ClvBySport> | null | undefined;
}) {
  const rows = Object.entries(bySport || {}).filter(
    ([, v]) => v && typeof v === "object" && typeof v.n === "number" && v.n > 0,
  );
  if (rows.length === 0) return null;
  // Sort by graded count desc so the dominant sport is first.
  rows.sort((a, b) => (b[1].n ?? 0) - (a[1].n ?? 0));
  return (
    <div className="mt-4">
      <div className="mb-1.5 text-[10px] uppercase tracking-wide text-slate-500">
        By sport
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wide text-slate-500">
            <th className="pb-1 font-medium">Sport</th>
            <th className="pb-1 font-medium text-right">Graded</th>
            <th className="pb-1 font-medium text-right">% beat</th>
            <th className="pb-1 font-medium text-right">Mean CLV</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {rows.map(([sport, v]) => {
            const neg = v.mean_clv_pct != null && v.mean_clv_pct < 0;
            return (
              <tr key={sport} className="text-slate-300">
                <td className="py-1.5 font-mono uppercase">{sport}</td>
                <td className="py-1.5 text-right font-mono tabular-nums">
                  {v.n}
                </td>
                <td className="py-1.5 text-right font-mono tabular-nums">
                  {v.pct_beat_close != null
                    ? fmtPct(v.pct_beat_close, false)
                    : "--"}
                </td>
                <td
                  className={
                    "py-1.5 text-right font-mono tabular-nums " +
                    (neg ? "text-red-400" : "text-slate-200")
                  }
                >
                  {v.mean_clv_pct != null ? fmtPct(v.mean_clv_pct) : "--"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-bg-subtle px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-lg tabular-nums text-slate-100">
        {value}
      </div>
    </div>
  );
}
