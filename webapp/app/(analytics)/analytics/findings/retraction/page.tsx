import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import { findingMeta } from "@/lib/analytics/og";
import { resolveResearchSourceDestination } from "@/lib/analytics/researchSourceDestinations";

export const metadata: Metadata = {
  title: "The Retraction Story",
  description: "Six withdrawn headline figures, with the measurement failure and published replacement where one exists.",
  ...findingMeta("retraction"),
};

type Retraction = {
  id: string;
  status: "withdrawn" | "superseded" | "withdrawn, no replacement";
  withdrawnMeasurement: string;
  defect: string;
  withdrawnOn: string;
  replacement: string;
  evidenceArtifact: string;
  evidenceSourceId: string;
};

export const RETRACTIONS: readonly Retraction[] = [
  {
    id: "pregame-return",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +18.38% pregame return figure computed on a market-following baseline",
    defect: "The evaluation CSV had no prediction column. The grader selected direction from the devigged close, used a fixed conversion unavailable in the recorded source, and tuned filters in sample. That is a market-follow artifact, not a model measurement.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
  {
    id: "end-of-third-quarter-brier",
    status: "superseded",
    withdrawnMeasurement: "withdrawn: 0.119 end-of-third-quarter Brier score",
    defect: "Two fourth-quarter-derived features entered a model that was predicting the fourth quarter, and the cited file reported a different figure. The original score therefore contained future information.",
    withdrawnOn: "2026-07-23",
    replacement: "Replacement measurement: leak-free walk-forward end-of-third-quarter Brier score 0.141 (unitless), published in JOB_EVIDENCE_PACKET.md on 2026-07-23.",
    evidenceArtifact: "state_conditioned_calibration.json",
    evidenceSourceId: "state_conditioned_calibration",
  },
  {
    id: "in-play-proxy",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +54.57% / 78.11% in-play accuracy figure measured against a lagged L5 proxy ceiling",
    defect: "The score used an L5 line proxy rather than a real closing reference. It described a soft proxy ceiling, not an externally validated measurement.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
  {
    id: "closing-line-movement",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +8.94pp closing-line movement calculation",
    defect: "The aggregate was circular: it used the same model-unused, devigged-direction corpus to define and grade the movement calculation. The denominator did not provide an independent comparison.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
  {
    id: "steals-blocks-overfit",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: steals and blocks training R^2 about 0.79, with leak-free holdout R^2 about 0.06",
    defect: "A leaky grid search inflated the training measurement before the holdout exposed the collapse. Corrective regularization now takes precedence over the stale tuned parameters.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
  {
    id: "assists-playoffs",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: assists conclusion after postseason stress testing",
    defect: "The measurement was regime-dependent: it failed in the playoffs, and an in-series play-by-play replay confirmed that the earlier conclusion did not hold there.",
    withdrawnOn: "2026-07-21",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
];

const SCOUT_QUESTIONS = [
  "What was the biggest result you had to retract?",
  "Do you keep retracted findings in the ledger or delete them?",
  "How many of your claims are verified versus null?",
];

const h1: CSSProperties = {
  fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)",
  lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8,
};
const lede: CSSProperties = {
  fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 680, marginTop: 16,
};
const truthBanner: CSSProperties = {
  marginTop: 28, padding: "14px 18px", background: "var(--paper-tint)", borderLeft: "2px solid var(--reject)",
  borderRadius: "var(--radius-card)", maxWidth: 680, fontFamily: "var(--font-mono)", fontSize: 12.5,
  color: "var(--ink-3)", lineHeight: 1.5,
};
const card: CSSProperties = {
  marginTop: 20, padding: "22px 24px", background: "var(--paper-raised)", border: "1px solid var(--rule)",
  borderRadius: "var(--radius-card)", boxShadow: "var(--shadow-card)", maxWidth: 680,
};
const cardHead: CSSProperties = { display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" };
const statusBadge: CSSProperties = {
  fontFamily: "var(--font-mono)", fontSize: 10.5, fontWeight: 700, letterSpacing: "0.08em", color: "var(--reject)",
  border: "1px solid var(--reject)", borderRadius: "var(--radius-chip)", padding: "2px 7px", textTransform: "uppercase",
  whiteSpace: "nowrap", flex: "0 0 auto",
};
const withdrawnLine: CSSProperties = {
  fontFamily: "var(--font-display)", fontSize: 18, lineHeight: 1.4, color: "var(--reject)",
  textDecoration: "line-through", textDecorationThickness: "1.5px", margin: 0,
};
const rowLabel: CSSProperties = {
  fontWeight: 700, fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--ink-3)",
  marginTop: 14, marginBottom: 4,
};
const rowBody: CSSProperties = { fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)" };
const replacementBody: CSSProperties = { ...rowBody, color: "var(--ink)" };
const evidenceLink: CSSProperties = {
  fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--ink-3)", textUnderlineOffset: 3,
};

export default function RetractionPage() {
  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Retraction</p>
      <h1 style={h1}>The Retraction Story</h1>
      <p style={lede}>
        These six headline figures were published, then withdrawn when their measurements failed.
        Each entry names the measurement, the defect, the withdrawal date, and the replacement only
        when a dated calibration measure exists.
      </p>
      <p style={truthBanner}>
        The source for this record is JOB_EVIDENCE_PACKET.md, published with this finding on
        2026-07-23. A withdrawn figure is historical documentation, never a current result.
      </p>

      <div style={{ marginTop: 8 }}>
        {RETRACTIONS.map((retraction) => {
          const evidenceHref = resolveResearchSourceDestination(retraction.evidenceSourceId).href;
          return (
          <article id={retraction.id} key={retraction.id} style={card}>
            <div style={cardHead}>
              <span style={statusBadge}>{retraction.status}</span>
              <h2 style={withdrawnLine}>{retraction.withdrawnMeasurement}</h2>
            </div>
            <p style={rowLabel}>Measurement failure</p>
            <p style={rowBody}>{retraction.defect}</p>
            <p style={rowLabel}>Withdrawal recorded</p>
            <p style={rowBody}>{retraction.withdrawnOn}</p>
            <p style={rowLabel}>Replacement</p>
            <p style={replacementBody}>{retraction.replacement}</p>
            <p style={rowLabel}>Evidence citation</p>
            <Link href={evidenceHref} style={evidenceLink}>
              {retraction.evidenceArtifact}
            </Link>
          </article>
          );
        })}
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        The record keeps measurement failures visible. A replacement belongs here only when the
        published source names the calibration measure, its unit, and its date.
      </p>

      <ScoutQuestions questions={SCOUT_QUESTIONS} heading="Ask Scout about this" />
    </div>
  );
}
