import type { ComparisonEntity } from "@/lib/analytics/comparisonData";
import { type PitchResultValue, pitchResultComparison } from "@/lib/analytics/pitchResultComparison";

type Props = { a: ComparisonEntity; b: ComparisonEntity; sourceHref: string };

function pitchCount(value: number | null): string { return value === null ? "Not reported" : value.toLocaleString("en-US"); }
function resultText(value: PitchResultValue, available: boolean): string {
  if (value.value !== null) return `${value.value.toFixed(1)}%`;
  return available && !value.serialized ? "Not published" : "Unavailable";
}

function ResultBar({ name, label, value, available, tone }: { name: string; label: string; value: PitchResultValue; available: boolean; tone: string }) {
  const text = resultText(value, available);
  return <div className="pitch-result-bar-cell"><span className="pitch-result-value">{text}</span>{value.value !== null ? <span className="pitch-result-track" role="img" aria-label={`${name} ${label}: ${text}`}><i className={tone} style={{ width: `${value.value}%` }} /></span> : <span className="pitch-result-track is-unavailable" aria-hidden="true" />}</div>;
}
function Axis({ name }: { name: string }) { return <span className="pitch-result-axis"><b>{name}</b><span aria-label={`${name} bar scale: 0%, 50%, 100%`}><i>0%</i><i>50%</i><i>100%</i></span></span>; }

export function PitchResultComparison({ a, b, sourceHref }: Props) {
  const comparison = pitchResultComparison(a, b);
  if (!comparison) return null;
  const sharedDate = comparison.sameAsOf === true;
  const evidence = [comparison.entities.a, comparison.entities.b];
  const supportNotes = Array.from(new Set(evidence.map((entity) => entity.floors).filter((floor): floor is string => floor?.toLowerCase().includes("sampling noise") === true)));
  return <section className="pitch-result-comparison" aria-labelledby="pitch-result-title">
    <div><span className="compare-section-label">MLB pitch context</span><h2 id="pitch-result-title">Recorded pitch-result mix</h2></div>
    <p className="pitch-result-intro">Published share of pitches recorded as Ball, Strike, or In play. Each bar uses the same 0-100% scale and the exact published percentage.</p>
    <div className="pitch-result-chart" aria-label="Recorded pitch-result shares">
      <div className="pitch-result-head"><span>Result</span><Axis name={a.name} /><Axis name={b.name} /></div>
      {comparison.rows.map((row) => <div className="pitch-result-row" key={row.key}><strong>{row.label}</strong><ResultBar name={a.name} label={row.label} value={row.a} available={comparison.entities.a.outcomeAvailable} tone={`pitch-result-${row.key}`} /><ResultBar name={b.name} label={row.label} value={row.b} available={comparison.entities.b.outcomeAvailable} tone={`pitch-result-${row.key}`} /></div>)}
    </div>
    <table className="pitch-result-table"><caption>Published pitch-result shares</caption><thead><tr><th scope="col">Result</th><th scope="col">{a.name}</th><th scope="col">{b.name}</th></tr></thead><tbody>{comparison.rows.map((row) => <tr key={row.key}><th scope="row">{row.label}</th><td>{resultText(row.a, comparison.entities.a.outcomeAvailable)}</td><td>{resultText(row.b, comparison.entities.b.outcomeAvailable)}</td></tr>)}</tbody></table>
    <div className="pitch-result-meta"><p><b>Published pitches:</b> {a.name} {pitchCount(comparison.entities.a.nPitches)}; {b.name} {pitchCount(comparison.entities.b.nPitches)}.</p>{supportNotes.map((floor) => { const names = evidence.filter((entity) => entity.floors === floor).map((entity) => entity.name); return <p className="pitch-result-source-note" key={floor}><b>{names.length > 1 ? "Shared source support note:" : "Source support note:"}</b> {names.length === 1 ? `${names[0]}: ` : null}{floor}</p>; })}<p>{comparison.definition} {comparison.denominator}</p><p>Categories are rounded independently to one decimal place. Missing categories have no published value.</p>{comparison.family === "team" ? <p>Teams are the pitching side in these source records.</p> : null}<details><summary>Methods and source details</summary><p><a href="https://baseballsavant.mlb.com/csv-docs" target="_blank" rel="noreferrer">Statcast CSV documentation</a> defines type codes B, S, and X. <a href={sourceHref} target="_blank" rel="noreferrer">Raw MLB atlas manifest</a></p><p>{comparison.note}</p><p>The cutoff is the source pull's maximum game date, not a per-record latest date or a full-season claim.</p>{comparison.entities.a.floors === comparison.entities.b.floors ? <p>{comparison.entities.a.floors || "No source floor was serialized."}</p> : <><p><b>{a.name}:</b> {comparison.entities.a.floors || "No source floor was serialized."}</p><p><b>{b.name}:</b> {comparison.entities.b.floors || "No source floor was serialized."}</p></>}</details><p>Source cutoff: {sharedDate ? comparison.entities.a.asOf || "not reported" : `${a.name}: ${comparison.entities.a.asOf || "not reported"}; ${b.name}: ${comparison.entities.b.asOf || "not reported"}`}</p></div>
  </section>;
}
