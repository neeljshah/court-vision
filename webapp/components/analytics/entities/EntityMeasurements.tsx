import { Receipt } from "@/components/analytics/Receipt";
import { PercentileBar } from "@/components/analytics/PercentileBar";
import type { ReactNode } from "react";
import type { EntityMeasurements as Measurements } from "@/lib/analytics/entityMeasurements";

type Props = { measurements: Measurements; sourceArtifact: string; asOf?: string };

function Distribution({ label, rows }: Measurements["distributions"][number]) {
  const total = rows.reduce((sum, row) => sum + row.share, 0) || 1;
  return <section style={{ marginTop: 22 }}>
    <h2 className="serif" style={{ fontWeight: 500, fontSize: 20, marginBottom: 9 }}>{label}</h2>
    <div role="img" aria-label={`${label} distribution`} style={{ display: "flex", height: 12, overflow: "hidden", borderRadius: 6, background: "var(--rule)" }}>
      {rows.map((row, i) => <span key={row.key} title={`${row.key}: ${row.share.toFixed(1)}%`} style={{ width: `${row.share / total * 100}%`, background: i % 2 ? "var(--signal)" : "var(--accent)" }} />)}
    </div>
    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 10, fontSize: 13 }}><tbody>
      {rows.map((row) => <tr key={row.key}><th scope="row" style={{ color: "var(--ink-2)", fontWeight: 400, textAlign: "left", padding: "3px 0" }}>{row.key}</th><td className="mono" style={{ textAlign: "right", padding: "3px 0" }}>{row.share.toFixed(1)}%</td></tr>)}
    </tbody></table>
  </section>;
}

export function EntityMeasurements({ measurements, sourceArtifact, asOf }: Props) {
  const { scalars, distributions, unavailable } = measurements;
  const expected = scalars.length + distributions.length + unavailable.length;
  return <section aria-label="Measurements">
    <dl style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 1, background: "var(--rule)", border: "1px solid var(--rule)", borderRadius: 12 }}>
      {scalars.map((item) => <div key={item.key} style={{ background: "var(--paper-raised)", padding: "14px 16px" }}>
        <dt style={{ fontSize: 11, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 600 }}>{item.label}</dt>
        <dd className="mono" style={{ margin: "7px 0", fontSize: "1.05rem", color: "var(--ink)" }}>{item.value}{typeof item.percentile === "number" ? <><PercentileBar pct={item.percentile} nRanked={item.nRanked} /><div style={{ fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--ink-3)", marginTop: 3 }}>pct {item.percentile} of {item.nRanked ?? "?"} measured</div></> : null}<Receipt sourceArtifact={sourceArtifact} asOf={asOf} verdict="descriptive_only" label="descriptive_only" value={item.value} /></dd>
      </div>)}
    </dl>
    {distributions.map(({ key, ...distribution }) => <Distribution key={key} {...distribution} />)}
    {unavailable.length ? <p style={{ margin: "16px 0 0", fontSize: 13, color: "var(--ink-3)", lineHeight: 1.5 }}>
      {unavailable.length} of {expected} expected measurements unavailable: {unavailable.map((item) => <span key={item.key} title={item.floor ? `Floor: ${item.floor}` : undefined}>{item.label}</span>).reduce<ReactNode[]>((out, item, i) => i ? [...out, ", ", item] : [item], [])}.
    </p> : null}
  </section>;
}

export default EntityMeasurements;
