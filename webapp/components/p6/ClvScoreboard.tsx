"use client";

import type { ReactNode } from "react";
import type { ClvScoreboard as Clv, ClvBySport } from "@/lib/p5api";
import { isUnavailable } from "@/lib/p5api";
import { Unavailable, Badge } from "./Primitives";
import { Panel, PanelHead, Num } from "@/components/ui/terminal";
import { fmtPct } from "@/lib/utils";

// ClvScoreboard -- the beat-the-close yardstick. CLV (better-number-than-close)
// is the only honest edge metric surfaced. No $ / ROI. Proxy closes flagged.
// asOf/stale are optional -- callers that poll (ClvScoreboardLive) wire a real
// fetch timestamp; presentational callers (GameDetail) omit them. Composes
// terminal.tsx's Panel/PanelHead directly (Primitives' Panel adapter doesn't
// carry asOf/stale) so this stays the flat Direction A container either way.
export function ClvScoreboard({
  clv,
  asOf,
  stale,
  extraRight,
}: {
  clv: Clv | null | undefined;
  asOf?: string | null;
  stale?: boolean;
  extraRight?: ReactNode;
}) {
  if (!clv || isUnavailable(clv)) {
    return (
      <Panel>
        <PanelHead title="CLV scoreboard (beat the close)" asOf={asOf} stale={stale} />
        <div className="p-4">
          <Unavailable reason={(clv as { reason?: string })?.reason} />
        </div>
      </Panel>
    );
  }
  const settled = clv.n_bets > 0;
  return (
    <Panel>
      <PanelHead
        title="CLV scoreboard (beat the close)"
        asOf={asOf}
        stale={stale}
        right={
          <span className="flex items-center gap-2">
            {clv.clv_is_proxy ? (
              <Badge tone="amber">
                proxy close{clv.n_proxy ? ` (n=${clv.n_proxy})` : ""}
              </Badge>
            ) : null}
            {extraRight}
          </span>
        }
      />
      <div className="p-4">
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
        {/* Mean CLV above is ALL-rows (may include proxy closes). When any proxy
            rows exist, surface the true-close-preferred median alongside it so
            the headline is never silently blended -- basis says which. */}
        {clv.n_proxy != null && clv.n_proxy > 0 && clv.median_clv_pct != null ? (
          <p className="mt-2 text-xs text-faint">
            median CLV ({clv.basis === "true_close" ? "true-close" : "incl. proxy"}
            ): {fmtPct(clv.median_clv_pct)} -- excludes {clv.n_proxy} proxy close
            {clv.n_proxy === 1 ? "" : "s"} when true-close rows exist
          </p>
        ) : null}
        {/* PT-P0-07: per-sport CLV breakdown -- a positive aggregate (e.g. NBA)
            must not mask a negative sport (e.g. soccer). Render each sport's own
            n / mean CLV / %-beat-close so the blend is honest. */}
        {settled ? <BySportBreakdown bySport={clv.by_sport} /> : null}
        {!settled ? (
          <p className="mt-3 text-xs text-faint">
            No settled bets yet -- CLV populates as paper bets grade against the
            close. No $ edge is claimed.
          </p>
        ) : null}
      </div>
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
    <div className="mt-4 overflow-x-auto">
      <div className="microlabel mb-1.5">By sport</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="microlabel text-left">
            <th className="px-3 py-1.5 font-medium">Sport</th>
            <th className="px-3 py-1.5 font-medium text-right">Graded</th>
            <th className="px-3 py-1.5 font-medium text-right">% beat</th>
            <th className="px-3 py-1.5 font-medium text-right">Mean CLV</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map(([sport, v]) => {
            const neg = v.mean_clv_pct != null && v.mean_clv_pct < 0;
            return (
              <tr key={sport} className="hover:bg-surface-2">
                <td className="px-3 py-1.5 font-data uppercase">{sport}</td>
                <td className="px-3 py-1.5 text-right">
                  <Num>{v.n}</Num>
                </td>
                <td className="px-3 py-1.5 text-right">
                  <Num>
                    {v.pct_beat_close != null
                      ? fmtPct(v.pct_beat_close, false)
                      : "--"}
                  </Num>
                </td>
                <td className="px-3 py-1.5 text-right">
                  <Num className={neg ? "text-down" : ""}>
                    {v.mean_clv_pct != null ? fmtPct(v.mean_clv_pct) : "--"}
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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border bg-surface-1 px-3 py-2.5">
      <div className="microlabel">{label}</div>
      <div className="mt-0.5">
        <Num className="text-lg">{value}</Num>
      </div>
    </div>
  );
}
