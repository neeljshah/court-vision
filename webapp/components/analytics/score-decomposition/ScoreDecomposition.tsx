import { Figure } from "@/components/analytics/charts/Figure";
import { linear } from "@/components/analytics/charts/scale";
import { formatDecompositionValue, type DecompositionRow, type DecompositionSport } from "@/lib/analytics/scoreDecomposition";

const COMPONENTS = [
  { key: "reliability", label: "Reliability", color: "var(--accent)" },
  { key: "resolution", label: "Resolution", color: "var(--signal)" },
  { key: "uncertainty", label: "Uncertainty", color: "var(--ink-3)" },
] as const;

function sportLabel(sport: string): string {
  return sport === "mlb" ? "MLB" : sport === "soccer_intl" ? "International soccer" : sport.replace(/_/g, " ");
}

function sideLabel(side: DecompositionRow["side"]): string {
  return side === "model" ? "Model" : "Market";
}

function rowId(sport: string, row: DecompositionRow): string {
  return `${sport}-${row.side}`;
}

function ComponentChart({ sports }: { sports: DecompositionSport[] }) {
  const rows = sports.flatMap(item => item.rows.map(row => ({ sport: item.sport, row })));
  const values = rows.flatMap(item => COMPONENTS.map(component => item.row[component.key] ?? 0));
  const maximum = Math.max(...values, 0.01);
  const width = Math.max(620, 120 + rows.length * 150);
  const height = 300;
  const sy = linear(0, maximum, 242, 38);
  return <svg className="sd-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Murphy decomposition components by sport and population" data-testid="score-decomposition-chart">
    {[0, maximum / 2, maximum].map(value => <g key={value}><line x1="58" x2={width - 24} y1={sy(value)} y2={sy(value)} className="sd-grid" /><text x="48" y={sy(value) + 4} textAnchor="end">{value.toFixed(3)}</text></g>)}
    {rows.map(({ sport, row }, index) => {
      const start = 76 + index * 150;
      return <g key={rowId(sport, row)}>
        {COMPONENTS.map((component, componentIndex) => {
          const value = row[component.key] ?? 0;
          const x = start + componentIndex * 32;
          return <rect key={component.key} x={x} y={sy(value)} width="24" height={242 - sy(value)} rx="2" fill={component.color}><title>{`${sportLabel(sport)} ${sideLabel(row.side)} ${component.label}: ${formatDecompositionValue(value)}`}</title></rect>;
        })}
        <text className="sd-axis" x={start + 44} y="262" textAnchor="middle">{sportLabel(sport)}</text>
        <text className="sd-axis" x={start + 44} y="278" textAnchor="middle">{sideLabel(row.side)}</text>
      </g>;
    })}
  </svg>;
}

export function ScoreDecomposition({ sports }: { sports: DecompositionSport[] }) {
  if (!sports.length) return <p className="sd-empty">No published score-decomposition rows are available in this snapshot.</p>;
  return <section className="sd-shell" aria-label="Brier score decomposition">
    <div className="sd-legend">{COMPONENTS.map(component => <span key={component.key}><i style={{ background: component.color }} />{component.label}</span>)}</div>
    <Figure source="public/data/showcase/murphy_decomposition.json" asOf="Published snapshot" title="Binned Murphy components" subtitle="Each group preserves a separate published model or market population. Resolution is shown as a component; the audit table keeps its subtraction explicit.">
      <ComponentChart sports={sports} />
    </Figure>
    <div className="sd-table-wrap" role="region" aria-label="Brier reconstruction audit" data-scroll-region>
      <table className="sd-table"><caption>Published Brier reconstruction audit</caption><thead><tr><th>Sport</th><th>Population</th><th>Brier</th><th>Reconstructed Brier</th><th>Remainder</th></tr></thead><tbody>{sports.flatMap(item => item.rows.map(row => <tr key={rowId(item.sport, row)}><td>{sportLabel(item.sport)}</td><td>{sideLabel(row.side)}</td><td>{formatDecompositionValue(row.brier)}</td><td>{formatDecompositionValue(row.reconstructedBrier)}</td><td>{formatDecompositionValue(row.reconstructedBrier)} - {formatDecompositionValue(row.brier)} = <strong>{formatDecompositionValue(row.remainder)}</strong></td></tr>))}</tbody></table>
    </div>
    <p className="sd-note">The reconstruction is computed from ten probability bins. A binned reconstruction can differ from the published Brier; this table reports that signed remainder without assigning a cause to it.</p>
    <p className="sd-source-fields">Source fields: murphy_decomposition.json -&gt; sports[sport].model_prob and market_prob: brier, reliability, resolution, uncertainty, reconstructed_brier. Remainder = reconstructed_brier - brier.</p>
  </section>;
}

export default ScoreDecomposition;
