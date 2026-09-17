import Link from "next/link";
import { Figure } from "@/components/analytics/charts/Figure";
import { VerdictDot } from "@/components/analytics/VerdictDot";
import { formatReliability, type CrossSportComparability as ComparabilityData, type CrossSportRow } from "@/lib/analytics/crossSportComparability";

function sportLabel(sport: string): string {
  if (sport === "mlb") return "MLB";
  if (sport === "nba") return "NBA";
  if (sport === "soccer_intl") return "International soccer";
  return "Tennis";
}

function published(value: boolean): string {
  return value ? "Published" : "Not published";
}

function ReliabilityChart({ rows }: { rows: CrossSportRow[] }) {
  const maximum = Math.max(...rows.flatMap(row => [row.reliability_model || 0, row.reliability_market || 0]), 0.01);
  const scale = (value: number) => 180 - (value / maximum) * 132;
  return <svg className="csc-chart" viewBox="0 0 640 230" role="img" aria-label="Comparable model and reference reliability components" data-testid="comparability-chart">
    {[0, maximum / 2, maximum].map(value => <g key={value}><line className="csc-grid" x1="64" x2="616" y1={scale(value)} y2={scale(value)} /><text x="54" y={scale(value) + 4} textAnchor="end">{value.toFixed(3)}</text></g>)}
    {rows.map((row, index) => {
      const start = 150 + index * 240;
      const model = row.reliability_model || 0;
      const reference = row.reliability_market || 0;
      return <g key={row.id} data-testid="comparable-chart-row"><rect x={start} y={scale(model)} width="54" height={180 - scale(model)} rx="3" fill="var(--accent)"><title>{`${sportLabel(row.sport)} model reliability ${formatReliability(row.reliability_model)}`}</title></rect><rect x={start + 66} y={scale(reference)} width="54" height={180 - scale(reference)} rx="3" fill="var(--signal)"><title>{`${sportLabel(row.sport)} reference reliability ${formatReliability(row.reliability_market)}`}</title></rect><text className="csc-axis" x={start + 60} y="202" textAnchor="middle">{sportLabel(row.sport)}</text><text className="csc-axis" x={start + 60} y="218" textAnchor="middle">n={row.n}</text></g>;
    })}
  </svg>;
}

export function CrossSportComparability({ data }: { data: ComparabilityData }) {
  return <div className="csc-shell">
    <section className="csc-section" aria-labelledby="capability-heading">
      <h2 id="capability-heading">Published measurement capability</h2>
      <p>Availability is derived from the published row fields. A null value remains not published; it is never treated as zero.</p>
      <div className="csc-table-wrap" role="region" aria-label="Cross-sport capability matrix" data-scroll-region><table className="csc-table"><thead><tr><th>Sport</th><th>Model reliability score</th><th>Reference reliability</th><th>Reliability decomposition</th><th>Population</th></tr></thead><tbody>{data.capabilities.map(capability => <tr key={capability.sport}><th scope="row">{sportLabel(capability.sport)}</th><td>{published(capability.scoreAvailable)}</td><td>{published(capability.referenceAvailable)}</td><td>{published(capability.decompositionAvailable)}</td><td>{published(capability.populationAvailable)}</td></tr>)}</tbody></table></div>
    </section>
    <section className="csc-section" aria-labelledby="supported-heading">
      <h2 id="supported-heading">Supported reliability-component comparisons</h2>
      <p>These are the only rows with model and reference reliability components on the published 0-1 probability scale.</p>
      <div className="csc-legend"><span><i className="csc-model" />Model reliability</span><span><i className="csc-reference" />Reference reliability</span></div>
      <Figure source="public/data/showcase/kernel_transfer.json" asOf={data.generatedAt.slice(0, 10)} dateKind="snapshot" title="Comparable reliability components" subtitle="Each pair retains its published population size."><ReliabilityChart rows={data.comparableRows} /></Figure>
      <div className="csc-supported-list" aria-label="Comparable reliability rows">{data.comparableRows.map(row => <article key={row.id}><div><VerdictDot verdict="descriptive_only" /><strong>{sportLabel(row.sport)}</strong><span>{row.market}</span></div><p>Model {formatReliability(row.reliability_model)}; reference {formatReliability(row.reliability_market)}; n={row.n}.</p><Link href={row.evidence.href}>View {row.evidence.title}</Link></article>)}</div>
    </section>
    <section className="csc-section" aria-labelledby="unsupported-heading">
      <h2 id="unsupported-heading">Rows held outside the comparison</h2>
      <p>A common scale does not establish matched populations or transferability. These published rows do not have the compatible components required for this chart.</p>
      <div className="csc-unsupported-list">{data.unsupportedRows.map(row => <article key={row.id} data-testid="unsupported-row"><div className="csc-row-head"><VerdictDot verdict="not_testable" /><h3>{sportLabel(row.sport)}: {row.market}</h3></div><p><strong>Missing or incompatible measurement:</strong> {row.unavailableMeasurement}</p><p className="csc-reason">{row.comparability_reason}</p><p className="csc-row-meta">Population n={row.n}</p><Link href={row.evidence.href}>View {row.evidence.title}</Link></article>)}</div>
    </section>
  </div>;
}

export default CrossSportComparability;
