// The Retraction Story, restyled for the Reading Room -- DESIGN Sec 1 + 4 + 11.
// THE ONLY page in the analytics product where the six retracted numbers
// render, and they render only here, inside explicit retraction framing that
// cites docs/JOB_EVIDENCE_PACKET.md (the single truth-source). The six rows
// below are the SAME verbatim table already shipped on the terminal's
// /evidence/retraction-story page (transcribed there from JOB_EVIDENCE_PACKET
// s3/s4) -- reused here rather than re-derived, so the two products can never
// silently disagree on what was retracted. Pure static prose: no showcase JSON
// read, so nothing here can be missing on a fresh clone. --reject (red) is used
// below -- the one context DESIGN Sec 1 allows it in.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "The Retraction Story",
  description:
    "Six retracted headline numbers, each paired with its honest, calibration-only replacement. Cites docs/JOB_EVIDENCE_PACKET.md.",
  ...findingMeta("retraction"),
};

const PACKET_ASOF = "2026-07-23";

type Retraction = {
  retracted: string;
  whatWasWrong: string;
  proofArtifact: string;
  honestReplacement: string;
};

// Transcribed verbatim from JOB_EVIDENCE_PACKET s3/s4 -- the canonical
// retracted-vs-honest table. Static and canonical, so a hardcoded const beats
// a parser; update here (and on the terminal's twin page) if the packet's
// table ever changes.
const RETRACTIONS: Retraction[] = [
  {
    retracted: "+18.38% pregame ROI on 1,535 walk-forward bets vs real closing lines",
    whatWasWrong:
      "Market-follow artifact, confirmed at the source-code level. The grader picked bet direction from the market's own devigged lean and never read the model (the eval CSV had no prediction column), priced at a flat -110 that real books do not offer, and tuned its filters in-sample on the same file.",
    proofArtifact: "JOB_EVIDENCE_PACKET s4 (model's own unfiltered number: -2.00%)",
    honestReplacement:
      "Roughly break-even-minus-vig vs real closing lines. Every candidate edge, including assists, was ultimately rejected or retracted by the same gates.",
  },
  {
    retracted: "0.119 end-of-Q3 in-play Brier, \"inside Pinnacle's range\"",
    whatWasWrong:
      "Leak-inflated and mis-sourced. Two features were computed from fourth-quarter data, so the model predicting Q4 was peeking at Q4; the cited file actually reported 0.1354, a different number.",
    proofArtifact:
      "JOB_EVIDENCE_PACKET s3 (leak-free re-run; controlled A/B ~4% relative inflation)",
    honestReplacement:
      "Leak-free walk-forward end-of-Q3 Brier ~0.141, after removing the Q4 feature leak found in the pipeline. Framed as a leak caught, not a competitive number.",
  },
  {
    retracted: "+54.57% ROI / 78.11% hit on 55,073 in-play bets",
    whatWasWrong:
      "Graded against an L5 line proxy, not real closing lines. A model-quality ceiling on a soft proxy, never a tradeable result.",
    proofArtifact: "JOB_EVIDENCE_PACKET s4",
    honestReplacement:
      "On a soft L5 proxy the in-play backtest reaches that ceiling. Treated strictly as a model-quality ceiling, never as realized edge.",
  },
  {
    retracted: "Aggregate CLV +8.94pp",
    whatWasWrong:
      "Circular -- computed on the same model-unused, devig-direction corpus. No real Pinnacle-close CLV exists yet; a full-season backtest shows CLV about zero vs real closes.",
    proofArtifact: "JOB_EVIDENCE_PACKET s4 (full-season backtest: CLV ~= 0 vs real closes)",
    honestReplacement:
      "Real closing-line CLV cannot be measured yet. The methodology that will measure it exists; no CLV figure is quoted until it can be.",
  },
  {
    retracted: "Steals/blocks prop grid search: training R^2 ~0.79",
    whatWasWrong:
      "Textbook leakage: the ~0.79 training R^2 collapsed to ~0.06 on a leak-free holdout.",
    proofArtifact:
      "src/prediction/prop_cv_split.py (documents the gap; hard-codes corrective regularization)",
    honestReplacement:
      "Caught and hard-corrected a leakage-driven overfit. The corrective regularization takes precedence over the stale tuned parameters, so the mistake cannot silently reappear.",
  },
  {
    retracted: "The assists ROI edge (the strongest surviving candidate)",
    whatWasWrong:
      "Regime-dependent -- it broke in the playoffs -- and retracted 2026-07-21. Under the no-edge rail, no dollar/ROI edge is claimed anywhere.",
    proofArtifact: "JOB_EVIDENCE_PACKET s3 (historical record only, in the gate artifacts)",
    honestReplacement:
      "No dollar or ROI edge is claimed anywhere. The historical measurement remains only as a record of the stress-testing methodology.",
  },
];

const SCOUT_QUESTIONS = [
  "What was the biggest result you had to retract?",
  "Do you keep retracted findings in the ledger or delete them?",
  "How many of your claims are verified versus null?",
];

const h1: CSSProperties = {
  fontFamily: "var(--font-display)",
  fontWeight: 500,
  fontSize: "clamp(2rem,4vw,2.75rem)",
  lineHeight: 1.08,
  letterSpacing: "-.015em",
  color: "var(--ink)",
  marginTop: 8,
};
const lede: CSSProperties = {
  fontSize: 18,
  lineHeight: 1.6,
  color: "var(--ink-2)",
  maxWidth: 680,
  marginTop: 16,
};
const truthBanner: CSSProperties = {
  marginTop: 28,
  padding: "14px 18px",
  background: "var(--paper-tint)",
  borderLeft: "2px solid var(--reject)",
  borderRadius: "var(--radius-card)",
  maxWidth: 680,
  fontFamily: "var(--font-mono)",
  fontSize: 12.5,
  color: "var(--ink-3)",
  lineHeight: 1.5,
};
const card: CSSProperties = {
  marginTop: 20,
  padding: "22px 24px",
  background: "var(--paper-raised)",
  border: "1px solid var(--rule)",
  borderRadius: "var(--radius-card)",
  boxShadow: "var(--shadow-card)",
  maxWidth: 680,
};
// Strikethrough + red alone is a hairline a fast scroll can miss, misreading a
// retracted figure as an achievement. Pair every struck line with an explicit
// RETRACTED badge so the status survives the skim (no number changes).
const retractHead: CSSProperties = { display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" };
const retractTag: CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 10.5,
  fontWeight: 700,
  letterSpacing: "0.1em",
  color: "var(--reject)",
  border: "1px solid var(--reject)",
  borderRadius: "var(--radius-chip)",
  padding: "2px 7px",
  textTransform: "uppercase",
  whiteSpace: "nowrap",
  flex: "0 0 auto",
};
const retractedLine: CSSProperties = {
  fontFamily: "var(--font-display)",
  fontSize: 18,
  lineHeight: 1.4,
  color: "var(--reject)",
  textDecoration: "line-through",
  textDecorationThickness: "1.5px",
  margin: 0,
};
const rowLabel: CSSProperties = {
  fontWeight: 700,
  fontSize: 11,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--ink-3)",
  marginTop: 14,
  marginBottom: 4,
};
const rowBody: CSSProperties = { fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)" };
const proofMono: CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 12,
  color: "var(--ink-3)",
};
const honestBody: CSSProperties = {
  fontSize: 14.5,
  lineHeight: 1.6,
  color: "var(--ink)",
};

export default function RetractionPage() {
  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Retraction</p>
      <h1 style={h1}>The Retraction Story</h1>
      <p style={lede}>
        The most persuasive thing on this site is not a winning number &mdash; it is the
        pile of losing ones, kept on purpose. These six headline figures were each
        published once, then taken apart by the same instruments that built the
        system, and every replacement below is calibration-only: no dollar, ROI, or
        edge figure is claimed anywhere on this site.
      </p>
      <p style={truthBanner}>
        The single truth-source for every figure below is docs/JOB_EVIDENCE_PACKET.md
        (packet as_of {PACKET_ASOF}). These six numbers appear here, and only here,
        inside this retraction framing &mdash; see{" "}
        <Link href="/analytics/the-loop">What verified means</Link> for the discipline
        that produced this table.
      </p>

      <div style={{ marginTop: 8 }}>
        {RETRACTIONS.map((r) => (
          <article key={r.retracted} style={card}>
            <div style={retractHead}>
              <span style={retractTag}>Retracted</span>
              <p style={retractedLine}>{r.retracted}</p>
            </div>
            <p style={rowLabel}>What was wrong</p>
            <p style={rowBody}>{r.whatWasWrong}</p>
            <p style={rowLabel}>Proof artifact</p>
            <p style={proofMono}>{r.proofArtifact}</p>
            <p style={rowLabel}>Honest replacement</p>
            <p style={honestBody}>{r.honestReplacement}</p>
          </article>
        ))}
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        The through-line: against real closing lines the market is efficient, the
        model is break-even-minus-vig, and every candidate edge, including the
        strongest one, was rejected or retracted by its own gates. That is the
        honest, correct result for an efficient market &mdash; and the harnesses that
        prove it are the same ones that took these six numbers apart.
      </p>

      <ScoutQuestions questions={SCOUT_QUESTIONS} heading="Ask Scout about this" />
    </div>
  );
}
