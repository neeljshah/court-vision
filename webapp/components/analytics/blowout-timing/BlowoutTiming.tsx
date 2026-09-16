import { Figure } from "@/components/analytics/charts/Figure";
import type { BlowoutTimingSport, BlowoutTimingThreshold } from "@/lib/analytics/blowoutTiming";

const SOURCE = "public/data/showcase/blowout_dynamics.json";

function sportLabel(sport: string): string {
  if (sport === "mlb") return "MLB";
  if (sport === "soccer_intl") return "International soccer";
  return sport.replace(/_/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function percent(value: number | null): string {
  return value === null ? "Not published" : `${(value * 100).toFixed(1)}%`;
}

function clock(value: number | null, unit: string): string {
  return value === null ? "Not published" : `${value.toFixed(2).replace(/\.00$/, "")} ${unit}`;
}

function timingDomain(rows: BlowoutTimingThreshold[]): number {
  return Math.max(1, ...rows.flatMap(row => [row.p25, row.median, row.p75].filter((value): value is number => value !== null)));
}

function ThresholdLabel({ row, unit }: { row: BlowoutTimingThreshold; unit: string }) {
  return <span className="bt-threshold mono">{row.threshold} {unit}</span>;
}

function Eligibility({ sport }: { sport: BlowoutTimingSport }) {
  return <p className="bt-eligibility">
    Published eligibility: <span className="mono">{sport.nGamesRaw.toLocaleString()} raw games</span>,
    {" "}<span className="mono">{sport.nGamesUsable.toLocaleString()} usable games</span> with at least
    {" "}<span className="mono">{sport.minTicksFloor.toLocaleString()} parseable score ticks</span>; each threshold
    needs <span className="mono">{sport.minGamesPerThreshold?.toLocaleString() || "the published floor"} decided games</span>{" "}
    for clock quartiles.
  </p>;
}

function IncidencePanel({ sport }: { sport: BlowoutTimingSport }) {
  return <section className="bt-panel" aria-labelledby={`bt-incidence-${sport.sport}`}>
    <h3 id={`bt-incidence-${sport.sport}`}>Incidence</h3>
    <p className="bt-panel-copy">Games in which this margin became permanent, out of all published games for the sport.</p>
    <p className="bt-unit-line">Margin unit: <span className="mono">{sport.unit}</span> | Clock field: <span className="mono">{sport.clockField}</span></p>
    <div className="bt-rows" role="list" aria-label={`${sportLabel(sport.sport)} incidence by threshold`}>
      {sport.thresholds.map(row => <div className={`bt-row${row.masked ? " bt-is-masked" : ""}`} key={row.threshold} role="listitem" data-masked={row.masked || undefined}>
        <ThresholdLabel row={row} unit={sport.unit} />
        <div className="bt-bar-track" aria-hidden="true"><span className="bt-incidence-bar" style={{ width: `${(row.incidence ?? 0) * 100}%` }} /></div>
        <span className="bt-value mono">{row.nGamesDecided.toLocaleString()} / {row.nGamesTotal.toLocaleString()} ({percent(row.incidence)})</span>
        {row.masked && <span className="bt-mask-reason">{row.maskReason}</span>}
      </div>)}
    </div>
  </section>;
}

function TimingPanel({ sport }: { sport: BlowoutTimingSport }) {
  const domain = timingDomain(sport.thresholds);
  return <section className="bt-panel" aria-labelledby={`bt-timing-${sport.sport}`}>
    <h3 id={`bt-timing-${sport.sport}`}>Conditional timing</h3>
    <p className="bt-panel-copy">P25, median, and P75 of the clock only among games where the threshold became permanent.</p>
    <p className="bt-unit-line">Margin unit: <span className="mono">{sport.unit}</span> | Clock field: <span className="mono">{sport.clockField}</span></p>
    <div className="bt-rows" role="list" aria-label={`${sportLabel(sport.sport)} conditional timing by threshold`}>
      {sport.thresholds.map(row => {
        const left = row.p25 === null ? 0 : row.p25 / domain * 100;
        const width = row.p25 === null || row.p75 === null ? 0 : (row.p75 - row.p25) / domain * 100;
        const median = row.median === null ? 0 : row.median / domain * 100;
        return <div className={`bt-row${row.masked ? " bt-is-masked" : ""}`} key={row.threshold} role="listitem" data-masked={row.masked || undefined}>
          <ThresholdLabel row={row} unit={sport.unit} />
          {row.masked ? <span className="bt-mask-reason">{row.maskReason}</span> : <><div className="bt-bar-track bt-range-track" aria-hidden="true"><span className="bt-range-bar" style={{ left: `${left}%`, width: `${width}%` }} /><span className="bt-median-dot" style={{ left: `${median}%` }} /></div><span className="bt-value mono">{clock(row.p25, sport.clockField)} / {clock(row.median, sport.clockField)} / {clock(row.p75, sport.clockField)}</span></>}
        </div>;
      })}
    </div>
    <p className="bt-scale-note">Timing bars are scaled separately by sport. Innings and minutes are not combined.</p>
  </section>;
}

function CompactRows({ sport }: { sport: BlowoutTimingSport }) {
  return <div className="bt-compact-rows" role="list" aria-label={`${sportLabel(sport.sport)} compact threshold details`}>
    {sport.thresholds.map(row => <div className={`bt-compact-row${row.masked ? " bt-is-masked" : ""}`} key={row.threshold} role="listitem" data-masked={row.masked || undefined}>
      <ThresholdLabel row={row} unit={sport.unit} />
      <span className="bt-compact-incidence">{row.nGamesDecided.toLocaleString()} / {row.nGamesTotal.toLocaleString()} ({percent(row.incidence)})</span>
      <span className="bt-compact-timing">{row.masked ? row.maskReason : `${clock(row.p25, sport.clockField)} / ${clock(row.median, sport.clockField)} / ${clock(row.p75, sport.clockField)}`}</span>
    </div>)}
  </div>;
}

export function BlowoutTiming({ sports }: { sports: BlowoutTimingSport[] }) {
  return <div className="bt-sports">
    {sports.map(sport => <section className="bt-sport" key={sport.sport} aria-labelledby={`bt-${sport.sport}`}>
      <h2 id={`bt-${sport.sport}`}>{sportLabel(sport.sport)}</h2>
      <Figure source={SOURCE} asOf="published snapshot" title={`${sportLabel(sport.sport)} lasting-lead frequency and timing`} subtitle={`Thresholds are expressed in ${sport.unit}; the reported clock is ${sport.clockField}.`} verdict="descriptive_only">
        <Eligibility sport={sport} />
        <div className="bt-panels"><IncidencePanel sport={sport} /><TimingPanel sport={sport} /></div>
        <CompactRows sport={sport} />
      </Figure>
    </section>)}
  </div>;
}

export default BlowoutTiming;
