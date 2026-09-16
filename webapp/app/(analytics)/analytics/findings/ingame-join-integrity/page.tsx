import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { findingMeta } from "@/lib/analytics/og";
import { loadIngameIntegrityReceipt, loadIngameRegenerationReceipt } from "./ingameJoinIntegrity.server";
import { base } from "@/lib/analytics/dashboardTypes";
import { buildIngameJoinIntegrityFinding } from "./ingameJoinIntegrity";

export const metadata: Metadata = {
  title: "MLB in-game join integrity",
  description: "A dated account of mixed-game MLB tick files, incomplete state rows, and the revision-2 calibration artifacts rebuilt from the segment-clean corpus.",
  ...findingMeta("ingame-join-integrity"),
};

const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 760, marginTop: 16 };
const section: CSSProperties = { marginTop: 32, maxWidth: 900 };
const tableHead: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", verticalAlign: "bottom" };
const tableCell: CSSProperties = { padding: "12px 14px", borderBottom: "1px solid var(--rule)", color: "var(--ink-2)", fontSize: 14, verticalAlign: "top" };
const note: CSSProperties = { marginTop: 16, padding: "14px 18px", border: "1px solid var(--rule)", borderLeft: "3px solid var(--signal)", borderRadius: "var(--radius-card)", background: "var(--paper-tint)", color: "var(--ink-2)", fontSize: 14, lineHeight: 1.6, maxWidth: 800 };

export default function IngameJoinIntegrityPage() {
  const receipt = loadIngameIntegrityReceipt();
  const regeneration = loadIngameRegenerationReceipt();
  const finding = buildIngameJoinIntegrityFinding(receipt, regeneration);
  return <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
    <p className="overline">Findings / Data integrity</p>
    <h1 style={h1}>MLB in-game calibration now runs on a segment-clean corpus.</h1>
    <p style={lede}>This check, measured {finding.measuredOn}, found that a portion of the MLB in-game corpus joins ticks from consecutive-day games and applies one outcome label across them. The corpus has since been re-segmented so that one stored file holds one real game, and the affected artifacts were rebuilt from it. The published MLB and international soccer numbers are now revision {finding.regeneration.revision}; the revision 1 values measured here are withdrawn and kept in the regeneration receipt.</p>
    <p className="mono" style={{ marginTop: 12, color: "var(--ink-3)", fontSize: 12 }}>Receipt v{receipt.version} / <a href={`${base}/data/audits/mlb-ingame-integrity.json`}>published incident receipt</a> / <a href={`${base}/data/audits/mlb-ingame-regeneration.json`}>regeneration receipt</a> / {finding.method}</p>

    <section style={section} aria-labelledby="measured-counts">
      <h2 id="measured-counts" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>What was measured</h2>
      <div role="region" aria-label="Corpus integrity counts" data-scroll-region style={{ overflowX: "auto", marginTop: 12 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1020 }}>
          <thead><tr><th style={tableHead}>Sport</th><th style={tableHead}>Files</th><th style={tableHead}>Ticks</th><th style={tableHead}>Mixed files</th><th style={tableHead}>Mismatched ticks</th><th style={tableHead}>No game state</th><th style={tableHead}>Truncated games</th><th style={tableHead}>Label disagreements</th></tr></thead>
          <tbody>{finding.counts.map(row => <tr key={row.sport}><th scope="row" style={{ ...tableCell, color: "var(--ink)", fontWeight: 600 }}>{row.sport}</th><td className="mono" style={tableCell}>{row.files}</td><td className="mono" style={tableCell}>{row.ticks}</td><td className="mono" style={tableCell}>{row.mixedFiles}</td><td className="mono" style={tableCell}>{row.mismatchedTicks}</td><td className="mono" style={tableCell}>{row.statelessTicks}</td><td className="mono" style={tableCell}>{row.truncatedGames}</td><td style={tableCell}>{row.disagreements}</td></tr>)}</tbody>
        </table>
      </div>
      <p style={note}>{finding.leaderAgreement}</p>
    </section>

    <section style={section} aria-labelledby="tick-agreement">
      <h2 id="tick-agreement" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>Tick-level agreement</h2>
      <p style={{ ...lede, fontSize: 15 }}>The comparison is limited to late innings, defined here as inning 7+ and to ticks where a leading side can be assessed.</p>
      <div role="region" aria-label="Tick-level label agreement" data-scroll-region style={{ overflowX: "auto", marginTop: 12 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}>
          <thead><tr><th style={tableHead}>Population</th><th style={tableHead}>Leading-side label agreement</th><th style={tableHead}>Support</th></tr></thead>
          <tbody>{finding.agreement.map(row => <tr key={row.population}><th scope="row" style={{ ...tableCell, color: "var(--ink)", fontWeight: 600 }}>{row.population}</th><td className="mono" style={tableCell}>{row.frequency.toFixed(4)}</td><td className="mono" style={tableCell}>n = {row.n.toLocaleString("en-US")}</td></tr>)}</tbody>
        </table>
      </div>
    </section>

    <section style={section} aria-labelledby="regeneration">
      <h2 id="regeneration" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>What the regeneration changed</h2>
      <p style={{ ...lede, fontSize: 15 }}>{finding.regeneration.method} Every figure below is the published headline of one artifact before and after that rebuild, measured {finding.regeneration.measuredOn} on <span className="mono">{finding.regeneration.corpus}</span>.</p>
      <div role="region" aria-label="Artifact headline before and after regeneration" data-scroll-region style={{ overflowX: "auto", marginTop: 12 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 960 }}>
          <thead><tr><th style={tableHead}>Artifact</th><th style={tableHead}>Population</th><th style={tableHead}>n before</th><th style={tableHead}>n after</th><th style={tableHead}>Headline before (revision 1, withdrawn)</th><th style={tableHead}>Headline after (revision 2)</th></tr></thead>
          <tbody>{finding.regeneration.rows.map(row => <tr key={row.artifact}><th scope="row" className="mono" style={{ ...tableCell, color: "var(--ink)", fontWeight: 600 }}>{row.artifact}</th><td style={tableCell}>{row.population}</td><td className="mono" style={tableCell}>{row.nBefore}</td><td className="mono" style={tableCell}>{row.nAfter}</td><td style={tableCell}>{row.headlineBefore}</td><td style={tableCell}>{row.headlineAfter}</td></tr>)}</tbody>
        </table>
      </div>
      <p style={note}>{finding.regeneration.checkerVerdict}</p>
      {finding.regeneration.reading.map(paragraph => <p key={paragraph} style={{ ...lede, fontSize: 15 }}>{paragraph}</p>)}
      <p className="mono" style={{ marginTop: 12, fontSize: 12 }}><a href={`${base}/data/audits/mlb-ingame-regeneration.json`}>Read the full regeneration receipt</a></p>
    </section>

    <section style={section} aria-labelledby="exposed-artifacts"><h2 id="exposed-artifacts" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>Affected calibration artifacts</h2><p style={{ ...lede, fontSize: 15 }}>The receipt records these artifacts against outcome labels. Their MLB and international soccer rows were rebuilt from the segment-clean corpus and now read revision 2.</p><ul className="mono" style={{ columns: "repeat(auto-fit,minmax(230px,1fr))", marginTop: 14, paddingLeft: 20, color: "var(--ink-2)", fontSize: 13 }}>{finding.exposedArtifacts.map(id => <li key={id} style={{ marginBottom: 4 }}>{id}</li>)}</ul><p style={{ ...lede, fontSize: 14 }}>Timing artifacts under review: {finding.timingArtifacts.join(", ")}. {finding.timingNote}</p></section>
    <section style={section} aria-labelledby="status"><h2 id="status" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>Artifact status registry</h2><p style={{ ...lede, fontSize: 15 }}>Only non-clear artifact and sport rows are listed. NBA and tennis rows remain clear.</p><div role="region" aria-label="Artifact status registry" data-scroll-region style={{ overflowX: "auto", marginTop: 12 }}><table style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}><thead><tr><th style={tableHead}>Artifact</th><th style={tableHead}>Sport</th><th style={tableHead}>Status</th></tr></thead><tbody>{finding.statusRows.map(row => <tr key={`${row.artifact}-${row.sport}`}><th scope="row" className="mono" style={{ ...tableCell, color: "var(--ink)", fontWeight: 600 }}>{row.artifact}</th><td style={tableCell}>{row.sport}</td><td className="mono" style={tableCell}>{row.state}</td></tr>)}</tbody></table></div></section>
    <section style={section} aria-labelledby="clear-status"><h2 id="clear-status" className="serif" style={{ fontWeight: 500, fontSize: 24 }}>What clears the status</h2><ul style={{ ...lede, fontSize: 15, paddingLeft: 22 }}><li>Done: segment identity checks keep every tick within its real game, and the checker reports no label disagreement and no multi-game file on the segmented corpus.</li><li>Done: the affected artifacts were regenerated from that checked corpus and published as revision 2.</li><li>Outstanding: the timing artifacts listed above were not regenerated in this pass and stay under review.</li><li>Outstanding: the research papers still quote revision 1 numbers and must be re-audited against the regenerated artifacts.</li></ul></section>
  </div>;
}
