"use client";

import { useState } from "react";
import Link from "next/link";
import type { CountContextClass, CountContextData } from "@/lib/analytics/countContext";

function count(value: number | null): string { return value === null ? "Not published" : value.toLocaleString("en-US"); }
function pct(value: number | null): string { return value === null ? "Not published" : `${value.toFixed(2)}%`; }
function ratePct(value: number | null): string { return value === null ? "Not published" : `${(value * 100).toFixed(2)}%`; }

function ClassGroup({ title, classes }: { title: string; classes: CountContextClass[] }) {
  return <section className="cc-group" aria-label={title}><h2>{title}</h2><div>{classes.map(item => <article key={item.id}>
    <h3>{item.id}</h3><p>{item.definition}</p><dl><div><dt>Class n</dt><dd>{count(item.n)}</dd></div><div><dt>Pitch-type n</dt><dd>{count(item.pitchTypeN)}</dd></div></dl>
    {item.overlapping && <p className="cc-overlap">Overlapping view; it is not additive with the partition.</p>}
  </article>)}</div></section>;
}

export function CountContext({ data }: { data: CountContextData }) {
  const [classId, setClassId] = useState(data.classes[0]?.id || "");
  const selected = data.classes.find(item => item.id === classId) || data.classes[0];
  if (!selected) return <p className="cc-empty">No published count-class rows are available in this snapshot.</p>;
  const partition = data.classes.filter(item => !item.overlapping);
  const lenses = data.classes.filter(item => item.overlapping);
  return <section className="cc-shell" aria-label="Count-context analysis">
    <div className="cc-selector" aria-label="Count class selector">{data.classes.map(item => <button key={item.id} type="button" aria-pressed={item.id === selected.id} onClick={() => setClassId(item.id)}>{item.id}</button>)}</div>
    <p className="cc-definition"><span className="mono">{selected.id}</span>: {selected.definition}</p>
    <section className="cc-mix" aria-labelledby="cc-mix-title"><div className="cc-section-head"><div><p>Selected class</p><h2 id="cc-mix-title">Published pitch mix</h2></div><dl><div><dt>Class n</dt><dd>{count(selected.n)}</dd></div><div><dt>Pitch-type n</dt><dd>{count(selected.pitchTypeN)}</dd></div></dl></div>
      <div className="cc-table-wrap" role="region" aria-label={`${selected.id} pitch mix table`} data-scroll-region><table><caption>Every published pitch type within {selected.id}</caption><thead><tr><th scope="col">Pitch type</th><th scope="col">Pitch count</th><th scope="col">Published frequency</th></tr></thead><tbody>{selected.pitchMix.map(item => <tr key={item.pitchType}><th scope="row">{item.pitchType}</th><td>{count(item.n)}</td><td>{pct(item.pct)}</td></tr>)}<tr className="cc-remainder"><th scope="row">Unpublished remainder</th><td>Not published</td><td>{pct(selected.remainderPct)}</td></tr></tbody></table></div>
      <p className="cc-note">Pitch frequency records the class-wide mix. The unpublished remainder is 100% minus the sum of the rounded published frequencies. For conditional next-pitch probability after a prior pitch, use <Link href={`/analytics/pitch-sequencing/?class=${encodeURIComponent(selected.id)}`}>the {selected.id} sequencing view</Link>.</p>
    </section>
    <section className="cc-outcomes" aria-labelledby="cc-outcomes-title"><p>Across all classes</p><h2 id="cc-outcomes-title">Outcome proxies with their own denominators</h2><p className="cc-note">Coded strikes are <code>type == S</code>; they are not a swinging-strike measurement. Each type outcome uses n_type, while in-zone rate uses n_zone.</p><div className="cc-table-wrap" role="region" aria-label="Outcome proxy comparison" data-scroll-region><table><thead><tr><th scope="col">Class</th><th scope="col">Coded strike rate, not swinging strike rate (n_type)</th><th scope="col">Ball rate (n_type)</th><th scope="col">In-play rate (n_type)</th><th scope="col">In-zone rate (n_zone)</th></tr></thead><tbody>{data.classes.map(item => <tr key={item.id}><th scope="row">{item.id}</th><td>{ratePct(item.outcomes.strikeRate)} <small>n {count(item.outcomes.nType)}</small></td><td>{ratePct(item.outcomes.ballRate)} <small>n {count(item.outcomes.nType)}</small></td><td>{ratePct(item.outcomes.inplayRate)} <small>n {count(item.outcomes.nType)}</small></td><td>{ratePct(item.outcomes.inZoneRate)} <small>n {count(item.outcomes.nZone)}</small></td></tr>)}</tbody></table></div></section>
    <section className="cc-classes" aria-label="Count-class definitions"><p>Count-class structure</p><ClassGroup title="Partition: behind, even, ahead" classes={partition} /><ClassGroup title="Overlapping views: two-strike and three-ball" classes={lenses} /></section>
    <p className="cc-source">Source fields: mlb_count_leverage.json -&gt; by_leverage_class[].n, pitch_type_n, pitch_mix_top, and outcome_proxies.</p>
  </section>;
}
