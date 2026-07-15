"use client";

// CoverageBars -- per-sport validation COVERAGE % (data points with a recorded
// verdict / [verdicts + untested-backlog-remaining]). This is the HONEST
// "getting better" axis: coverage grows as more data points are run through the
// leak-free gate and a verdict is recorded -- it is NOT an accuracy/edge climb.
// A REJECT counts toward coverage (a recorded reject is a SUCCESS). Each bar
// shows ship / reject / insufficient composition. NO $ field anywhere.

import { Panel, Badge } from "@/components/p6/Primitives";
import { InfoTip } from "@/components/depth";
import type { ProgressPerSport } from "@/lib/api";

const clampPct = (x: number) => Math.min(100, Math.max(0, x));

function SportRow({ sport, s }: { sport: string; s: ProgressPerSport }) {
  const cov = clampPct(s.coverage_pct ?? 0);
  const tested = s.n_tested ?? 0;
  // composition widths within the TESTED portion of the bar.
  const denom = tested || 1;
  const shipW = (s.n_ship / denom) * cov;
  const rejW = (s.n_reject / denom) * cov;
  const insW = (s.n_insufficient / denom) * cov;
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-mono uppercase tracking-wide text-foreground">
          {sport}
        </span>
        <span className="font-mono tabular-nums text-foreground">
          {cov.toFixed(1)}%
          <span className="ml-1 text-[10px] text-muted-foreground">
            ({tested} tested, {s.n_untested_remaining} untested)
          </span>
        </span>
      </div>
      <div
        role="meter"
        aria-label={`${sport} coverage ${cov.toFixed(1)} percent`}
        aria-valuenow={Number(cov.toFixed(1))}
        aria-valuemin={0}
        aria-valuemax={100}
        className="relative flex h-2.5 w-full overflow-hidden rounded-full bg-slate-800/70"
      >
        <span
          aria-hidden
          className="h-full bg-tier-a/70"
          style={{ width: `${shipW}%` }}
          title={`${s.n_ship} ship`}
        />
        <span
          aria-hidden
          className="h-full bg-slate-500/70"
          style={{ width: `${rejW}%` }}
          title={`${s.n_reject} reject (a success)`}
        />
        <span
          aria-hidden
          className="h-full bg-amber-500/60"
          style={{ width: `${insW}%` }}
          title={`${s.n_insufficient} insufficient`}
        />
      </div>
    </li>
  );
}

export function CoverageBars({
  perSport,
}: {
  perSport: Record<string, ProgressPerSport> | null;
}) {
  const sports = perSport ? Object.keys(perSport) : [];
  return (
    <Panel
      title="validation coverage by sport"
      right={
        <span className="inline-flex items-center gap-1.5">
          <Badge tone="slate">{sports.length} sports</Badge>
          <InfoTip
            text="Coverage = data points with a RECORDED gate verdict / (verdicts + untested backlog). It grows as more data is tested -- it is NOT an accuracy or edge climb. A REJECT counts as covered (a recorded reject is a SUCCESS, markets are efficient). Units / verdicts only, no $."
            ariaLabel="what is coverage?"
          />
        </span>
      }
    >
      {sports.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          no per-sport coverage available -- honest empty, never a fabricated bar.
        </p>
      ) : (
        <>
          <ul className="flex flex-col gap-3">
            {sports.map((sp) => (
              <SportRow key={sp} sport={sp} s={perSport![sp]} />
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm bg-tier-a/70" /> ship
              (calibration only)
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm bg-slate-500/70" /> reject
              (a success)
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm bg-amber-500/60" />{" "}
              insufficient
            </span>
          </div>
        </>
      )}
    </Panel>
  );
}
