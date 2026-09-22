import type { BrierPhaseCoverage } from "@/lib/analytics/brierPhaseCoverage";
import { sourceUrl } from "@/lib/analytics/dashboardTypes";

type Props = { coverage?: BrierPhaseCoverage[]; sport?: string; asOf?: string };
const count = (value: number | null) => value === null ? "Unavailable" : value.toLocaleString("en-US");

export function BrierPhaseCoveragePanel({ coverage, sport, asOf }: Props) {
  const entries = (coverage || []).filter(entry => !sport || entry.sport === sport);
  if (!entries.length) return null;
  return <section className="brier-phase-coverage" aria-label="Phase classification coverage">
    <header><div><p className="cv-eyebrow">Scored-row coverage</p><h3>How much history has a phase label?</h3></div>
      <span className="cv-footnote">Source as of {asOf || "date unrecorded"}</span></header>
    <p>Whole-corpus estimates include scored rows that do not appear in the published phase breakdown.</p>
    <div className="brier-phase-cards">{entries.map(entry => <article key={entry.sport} aria-label={`${entry.label} phase coverage`}>
      <h4>{entry.label}</h4>
      <div className="brier-phase-share"><strong>{entry.fraction === null ? "Unavailable" : `${(entry.fraction * 100).toFixed(2)}%`}</strong><span>of scored rows in published phases</span></div>
      {entry.fraction !== null && <div className="brier-phase-track" role="img" aria-label={`${entry.label}: ${count(entry.classified)} of ${count(entry.total)} scored rows in published phases`}>
        <span style={{ width: `${entry.fraction * 100}%` }} />
      </div>}
      <dl><div><dt>In published phases</dt><dd>{count(entry.classified)}</dd></div><div><dt>Outside the phase breakdown</dt><dd>{count(entry.outside)}</dd></div><div><dt>All scored rows</dt><dd>{count(entry.total)}</dd></div></dl>
      {entry.reason && <p className="brier-phase-unavailable">{entry.reason}</p>}
      {entry.total === 0 && !entry.reason && <p className="brier-phase-unavailable">No scored rows; the coverage percentage is undefined.</p>}
      <details><summary>Calculation and source fields</summary>
        <p>Coverage = sum of published phase counts / all scored rows. Outside = all scored rows - sum of phase counts.</p>
        <ul>{entry.sourcePaths.map(path => <li key={path}><code>{path}</code></li>)}</ul>
      </details>
    </article>)}</div>
    <p className="cv-footnote">These are scored in-game observations, not independent games. The source assigns each observation to at most one phase. Counts describe the full snapshot and do not change with the row search or measurement. Coverage does not measure forecast accuracy.</p>
    <p className="cv-footnote">The snapshot does not publish observation start and end dates here. Its publication date is not an observation window. The counts alone do not explain why a row is outside the phase breakdown.</p>
    <a href={sourceUrl("brier_skill_scores")} target="_blank" rel="noreferrer">Inspect phase counts in the published source</a>
  </section>;
}
