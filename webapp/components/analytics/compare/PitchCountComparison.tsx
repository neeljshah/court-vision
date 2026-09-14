import { type ComparisonEntity } from "@/lib/analytics/comparisonData";
import { pitchCountComparison } from "@/lib/analytics/pitchCountComparison";

type Props = { a: ComparisonEntity; b: ComparisonEntity; sourceHref: string };

function percent(value: number | null): string { return value === null ? "Not reported" : `${value.toFixed(1)}%`; }

function pitchCount(value: number | null): string { return value === null ? "Not reported" : value.toLocaleString("en-US"); }

function Bar({ name, rows }: { name: string; rows: Array<{ key: string; label: string; a: number | null; b: number | null }>; }) {
  const values = rows.map((row) => row.a);
  const label = rows.map((row, index) => `${row.label} ${percent(values[index])}`).join(", ");
  return <div className="pitch-count-bar-wrap"><span>{name}</span><div className="pitch-count-bar" role="img" aria-label={`${name}: ${label}`}>
    {rows.map((row) => <i key={row.key} className={`pitch-count-${row.key}`} style={{ width: `${row.a ?? 0}%` }} />)}
  </div></div>;
}

export function PitchCountComparison({ a, b, sourceHref }: Props) {
  const comparison = pitchCountComparison(a, b);
  if (!comparison) return null;
  const rowsForA = comparison.rows.map((row) => ({ ...row, a: row.a, b: row.b }));
  const rowsForB = comparison.rows.map((row) => ({ ...row, a: row.b, b: row.a }));
  const aComplete = rowsForA.every((row) => row.a !== null);
  const bComplete = rowsForB.every((row) => row.a !== null);
  const smallest = [comparison.entities.a, comparison.entities.b].filter((entity) => entity.nPitches === 7);
  const sharedDate = comparison.entities.a.asOf && comparison.entities.a.asOf === comparison.entities.b.asOf;

  return <section className="pitch-count-comparison" aria-labelledby="pitch-count-title">
    <div><span className="compare-section-label">MLB pitch context</span><h2 id="pitch-count-title">Recorded count context</h2></div>
    <p className="pitch-count-intro">Share of published pitches of each selected type by pre-pitch count context. The bars use source percentages as published and are not renormalized; rounded totals can differ from 100%.</p>
    <ul className="pitch-count-legend" aria-label="Count context color legend"><li><i className="pitch-count-pitcher_ahead" />Pitcher ahead</li><li><i className="pitch-count-even" />Even count</li><li><i className="pitch-count-pitcher_behind" />Pitcher behind</li></ul>
    <div className="pitch-count-bars">{aComplete ? <Bar name={a.name} rows={rowsForA} /> : <p className="pitch-count-incomplete">{a.name} has an incomplete published distribution; use the exact table values below.</p>}{bComplete ? <Bar name={b.name} rows={rowsForB} /> : <p className="pitch-count-incomplete">{b.name} has an incomplete published distribution; use the exact table values below.</p>}</div>
    <div className="pitch-count-table-wrap"><table className="pitch-count-table"><caption>Published pitch-type count context shares</caption><thead><tr><th scope="col">Count context</th><th scope="col">{a.name}</th><th scope="col">{b.name}</th></tr></thead><tbody>
      {comparison.rows.map((row) => <tr key={row.key}><th scope="row">{row.label}</th><td>{percent(row.a)}</td><td>{percent(row.b)}</td></tr>)}
    </tbody></table></div>
    <div className="pitch-count-meta">
      <p><b>Published pitches:</b> {a.name} {pitchCount(comparison.entities.a.nPitches)}; {b.name} {pitchCount(comparison.entities.b.nPitches)}.</p>
      <p>{comparison.definition} {comparison.denominator}</p>
      <p>{comparison.note}</p>
      {smallest.length ? <p><b>Smallest published category:</b> {smallest.map((entity) => `${entity.name} (n=7)`).join("; ")}. The source flags its smallest category as having high sampling noise.</p> : null}
      <details><summary>Published scope and limitations</summary>{comparison.entities.a.floors === comparison.entities.b.floors ? <p>{comparison.entities.a.floors || comparison.note}</p> : <><p><b>{a.name}:</b> {comparison.entities.a.floors || "Not reported"}</p><p><b>{b.name}:</b> {comparison.entities.b.floors || "Not reported"}</p></>}</details>
      <p>Source date: {sharedDate ? comparison.entities.a.asOf : `${a.name}: ${comparison.entities.a.asOf || "not reported"}; ${b.name}: ${comparison.entities.b.asOf || "not reported"}`}. <a href={sourceHref} target="_blank" rel="noreferrer">Raw pitch-type manifest</a></p>
    </div>
  </section>;
}
