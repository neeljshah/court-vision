import Link from "next/link";
import type { ReliabilityFindingSport } from "@/lib/analytics/reliabilityFinding";

function sportLabel(sport: string): string {
  return sport === "mlb" ? "MLB" : sport === "soccer_intl" ? "International soccer" : sport.replace(/_/g, " ");
}

function sourceLabel(source: "model" | "market"): string { return source === "model" ? "Model" : "Market"; }
function decimal(value: number): string { return value.toFixed(6); }
function count(value: number): string { return value.toLocaleString("en-US"); }

export function ReliabilityFinding({ sports }: { sports: ReliabilityFindingSport[] }) {
  if (!sports.length) return <p className="rf-empty">No published Murphy decomposition rows are available in this snapshot.</p>;
  return <section className="rf-shell" aria-label="Reliability decomposition finding">
    <p className="rf-headline">The published ten-bin reconstruction does not close identically for every measured sport, so its components do not establish a cause for the model-to-reference Brier difference.</p>
    <p className="rf-intro">Each reconstructed Brier is the published reliability minus resolution plus uncertainty. The signed remainder is derived as direct Brier minus reconstructed Brier; it is shown to make the ten-bin closure check inspectable.</p>
    {sports.map(sport => <section className="rf-sport" key={sport.sport} aria-labelledby={`${sport.sport}-heading`}>
      <h2 id={`${sport.sport}-heading`}>{sportLabel(sport.sport)}</h2>
      <p className="rf-denominator">Published denominators: {count(sport.nRows)} rows; each source has its own n below.</p>
      <div className="rf-table-wrap" role="region" aria-label={`${sportLabel(sport.sport)} reliability measurements`} data-scroll-region>
        <table className="rf-table"><caption>{sportLabel(sport.sport)} published decomposition audit</caption><thead><tr><th>Source</th><th>Direct Brier</th><th>Reconstructed Brier</th><th>Remainder (derived)</th><th>n rows</th><th>n</th><th>Reliability vs resolution</th></tr></thead><tbody>{sport.measurements.map(item => <tr key={item.source}>
          <td>{sourceLabel(item.source)}</td><td>{decimal(item.brier)}</td><td>{decimal(item.reconstructedBrier)}</td><td>{decimal(item.remainder)}</td><td>{count(sport.nRows)}</td><td>{count(item.n)}</td><td>Reliability is {item.reliabilityComparison} than resolution ({decimal(item.reliability)} vs {decimal(item.resolution)}).</td>
        </tr>)}</tbody></table>
      </div>
      <p className="rf-detail">A non-zero remainder means the published ten-bin identity does not close for this sport. The artifact alone does not identify why; binning, population differences, rounding, or another published-data limitation are possible.</p>
    </section>)}
    <p className="rf-links">Inspect the <Link href="/analytics/score-decomposition">score decomposition</Link> and the <Link href="/analytics/calibration">calibration inspector</Link> for the related published views.</p>
  </section>;
}

export default ReliabilityFinding;
