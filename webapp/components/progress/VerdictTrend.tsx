"use client";

// VerdictTrend -- the REAL cumulative gate-verdict trend over time, rebuilt from
// the funnel verdict file mtimes (reconstructed_history). The line goes up as
// VERDICTS ARE RECORDED, not as accuracy improves. It is honestly labelled and
// carries the standing note that the model itself is STATIC: nothing here is a
// live accuracy / edge climb. NO $ field anywhere.

import { Panel, Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";
import type { ProgressHistoryPoint } from "@/lib/api";

// A dependency-free inline SVG sparkline of cumulative verdicts.
function Sparkline({ pts }: { pts: ProgressHistoryPoint[] }) {
  const W = 320;
  const H = 64;
  const PAD = 4;
  const n = pts.length;
  if (n === 0) return null;
  const maxV = Math.max(1, ...pts.map((p) => p.n_verdicts_cumulative));
  const x = (i: number) =>
    n === 1 ? W / 2 : PAD + (i / (n - 1)) * (W - 2 * PAD);
  const y = (v: number) => H - PAD - (v / maxV) * (H - 2 * PAD);
  const line = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.n_verdicts_cumulative).toFixed(1)}`)
    .join(" ");
  const area = `${line} L${x(n - 1).toFixed(1)},${H - PAD} L${x(0).toFixed(1)},${H - PAD} Z`;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-16 w-full"
      role="img"
      aria-label={`cumulative recorded verdicts, ${pts[0].n_verdicts_cumulative} to ${pts[n - 1].n_verdicts_cumulative}`}
    >
      <path d={area} className="fill-tier-a/10" />
      <path d={line} className="fill-none stroke-tier-a/80" strokeWidth={1.5} />
      {pts.map((p, i) => (
        <circle
          key={i}
          cx={x(i)}
          cy={y(p.n_verdicts_cumulative)}
          r={1.6}
          className="fill-tier-a"
        >
          <title>{`${p.date_et}: ${p.n_verdicts_cumulative} verdicts`}</title>
        </circle>
      ))}
    </svg>
  );
}

export function VerdictTrend({
  history,
}: {
  history: ProgressHistoryPoint[] | null;
}) {
  const pts = history ?? [];
  const last = pts.length ? pts[pts.length - 1] : null;
  return (
    <Panel
      title="recorded verdicts over time (real trend)"
      right={
        <span className="inline-flex items-center gap-1.5">
          {last ? (
            <Badge tone="green">{last.n_verdicts_cumulative} verdicts</Badge>
          ) : null}
          <InfoTip
            text="This is a REAL cumulative count of leak-free gate verdicts recorded over time (rebuilt from funnel artifact mtimes). It rises as we TEST more, not as the model gets more accurate. The model itself is STATIC until the self-improve gate is enabled. No $ / accuracy / edge climb."
            ariaLabel="what does this trend show?"
          />
        </span>
      }
    >
      {pts.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          no recorded-verdict history yet -- honest empty, never a fabricated line.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <Sparkline pts={pts} />
          <div className="flex items-center justify-between font-mono text-[10px] text-muted-foreground">
            <span>{pts[0].date_et}</span>
            <span>{last?.date_et}</span>
          </div>
          <p className="text-[11px] leading-relaxed text-amber-600/80">
            This line is COVERAGE / verdicts recorded -- NOT a live accuracy or
            edge climb. The model is STATIC until a human enables the
            self-improve gate.
          </p>
        </div>
      )}
    </Panel>
  );
}
