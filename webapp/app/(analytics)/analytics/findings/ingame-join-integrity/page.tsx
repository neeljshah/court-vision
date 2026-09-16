import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { findingMeta } from "@/lib/analytics/og";
import { integrityFinding } from "./ingameJoinIntegrity";

export const metadata: Metadata = {
  title: "MLB in-game join integrity",
  description: "A dated account of mixed-game MLB tick files, incomplete state rows, and pending calibration artifact regeneration.",
  ...findingMeta("ingame-join-integrity"),
};

const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 760, marginTop: 16 };
const section: CSSProperties = { marginTop: 32, maxWidth: 900 };
const tableHead: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", verticalAlign: "bottom" };
const tableCell: CSSProperties = { padding: "12px 14px", borderBottom: "1px solid var(--rule)", color: "var(--ink-2)", fontSize: 14, verticalAlign: "top" };
const note: CSSProperties = { marginTop: 16, padding: "14px 18px", border: "1px solid var(--rule)", borderLeft: "3px solid var(--signal)", borderRadius: "var(--radius-card)", background: "var(--paper-tint)", color: "var(--ink-2)", fontSize: 14, lineHeight: 1.6, maxWidth: 800 };

export default function IngameJoinIntegrityPage() {
  return <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
    <p className="overline">Findings / Data integrity</p>
    <h1 style={h1}>MLB in-game calibration needs a segment-clean corpus.</h1>
    <p style={lede}>This check, measured {integrityFinding.measuredOn}, found that a portion of the MLB in-game corpus joins ticks from consecutive-day games and applies one outcome label across them. Until the affected artifacts are regenerated, every MLB calibration number on this site is measured on a partly mislabelled tick set.</p>

    <section style={section} aria-labelledby="measured-counts">
      <h2 id="measured-counts" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>What was measured</h2>
      <div role="region" aria-label="Corpus integrity counts" data-scroll-region style={{ overflowX: "auto", marginTop: 12 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 780 }}>
          <thead><tr><th style={tableHead}>Sport</th><th style={tableHead}>Files</th><th style={tableHead}>Ticks</th><th style={tableHead}>Contaminated</th><th style={tableHead}>No game state</th><th style={tableHead}>Truncated</th></tr></thead>
          <tbody>{integrityFinding.counts.map(row => <tr key={row.sport}><th scope="row" style={{ ...tableCell, color: "var(--ink)", fontWeight: 600 }}>{row.sport}</th><td style={tableCell}>{row.files}</td><td style={tableCell}>{row.ticks}</td><td style={tableCell}>{row.contaminated}</td><td style={tableCell}>{row.stateless}</td><td style={tableCell}>{row.truncated}</td></tr>)}</tbody>
        </table>
      </div>
      <p style={note}>{integrityFinding.leaderAgreement}</p>
    </section>

    <section style={section} aria-labelledby="tick-agreement">
      <h2 id="tick-agreement" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>Tick-level agreement</h2>
      <p style={{ ...lede, fontSize: 15 }}>The comparison is limited to late innings, defined here as inning 7+ and to ticks where a leading side can be assessed.</p>
      <div role="region" aria-label="Tick-level label agreement" data-scroll-region style={{ overflowX: "auto", marginTop: 12 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}>
          <thead><tr><th style={tableHead}>Population</th><th style={tableHead}>Leading-side label agreement</th><th style={tableHead}>Support</th></tr></thead>
          <tbody>{integrityFinding.agreement.map(row => <tr key={row.population}><th scope="row" style={{ ...tableCell, color: "var(--ink)", fontWeight: 600 }}>{row.population}</th><td className="mono" style={tableCell}>{row.agreement}</td><td className="mono" style={tableCell}>{row.n}</td></tr>)}</tbody>
        </table>
      </div>
    </section>

    <section style={section} aria-labelledby="cause"><h2 id="cause" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>Cause</h2><p style={{ ...lede, fontSize: 15 }}>{integrityFinding.cause}</p></section>
    <section style={section} aria-labelledby="exposed-artifacts"><h2 id="exposed-artifacts" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>Affected calibration artifacts</h2><p style={{ ...lede, fontSize: 15 }}>Thirteen of fifteen consumers bin a probability against the outcome label. The following artifacts are exposed to the mixed-game labels:</p><ul className="mono" style={{ columns: "repeat(auto-fit,minmax(230px,1fr))", marginTop: 14, paddingLeft: 20, color: "var(--ink-2)", fontSize: 13 }}>{integrityFinding.exposedArtifacts.map(id => <li key={id} style={{ marginBottom: 4 }}>{id}</li>)}</ul><p style={{ ...lede, fontSize: 14 }}>Not exposed: {integrityFinding.notExposedArtifacts.join(", ")}.</p></section>
    <section style={section} aria-labelledby="status"><h2 id="status" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>Status</h2><p style={note}>Pending regeneration from a segment-clean corpus. Regeneration will replace the affected MLB artifact measurements with labels joined within final game segments, then the calibration exhibits will publish the new measured values and their stated support.</p></section>
  </div>;
}
