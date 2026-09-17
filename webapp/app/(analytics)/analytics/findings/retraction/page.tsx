import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import { findingMeta } from "@/lib/analytics/og";
import { resolveResearchSourceDestination } from "@/lib/analytics/researchSourceDestinations";
import { RETRACTIONS } from "./retractions";

export const metadata: Metadata = {
  title: "Withdrawn measurements and corrections",
  description: "Six withdrawn headline figures, with the measurement failure, the withdrawal and editorial dates, and the published replacement where one exists.",
  ...findingMeta("retraction"),
};


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
const citationBox: CSSProperties = {
  marginTop: 4, padding: "10px 12px", background: "var(--paper-tint)", border: "1px solid var(--rule)",
  borderRadius: "var(--radius-card)", fontSize: 13, lineHeight: 1.55, color: "var(--ink-2)",
};
const citationMeta: CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--ink-3)", marginTop: 5 };

export default function RetractionPage() {
  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Retraction</p>
      <h1 style={h1}>Withdrawn measurements and corrections.</h1>
      <p style={lede}>
        These six headline figures were published, then withdrawn when their measurements failed.
        Each entry names the measurement, the defect, the date the withdrawal happened where the
        record states one, the editorial date of the record itself, and the replacement only when a
        dated calibration measure exists.
      </p>
      <p style={truthBanner}>
        The source for this record is JOB_EVIDENCE_PACKET.md, published with this finding on
        2026-07-23. That is an editorial date, not the date a withdrawal happened; where the packet
        does not state when a figure was withdrawn, this page says so rather than reusing the
        publication date. A withdrawn figure is historical documentation, never a current result.
      </p>

      <div style={{ marginTop: 8 }}>
        {RETRACTIONS.map((retraction) => {
          return (
          <article id={retraction.id} key={retraction.id} style={card}>
            <div style={cardHead}>
              <span style={statusBadge}>{retraction.status}</span>
              <h2 style={withdrawnLine}>{retraction.withdrawnMeasurement}</h2>
            </div>
            <p style={rowLabel}>Measurement failure</p>
            <p style={rowBody}>{retraction.defect}</p>
            <p style={rowLabel}>Withdrawal date</p>
            <p style={rowBody}>{retraction.eventDate || "date not recorded"}</p>
            <p style={rowLabel}>Editorial date of the record</p>
            <p style={rowBody}>{retraction.editorialDate}</p>
            <p style={rowLabel}>Replacement</p>
            <p style={replacementBody}>{retraction.replacement}</p>
            <p style={rowLabel}>Evidence citation</p>
            <div style={citationBox}>
              <p><strong style={{ color: "var(--ink)" }}>No published evidence document.</strong> {retraction.citation.document} is the cited withdrawal record, but it is not published on this site.</p>
              <p style={citationMeta}>Section: {retraction.citation.section}</p>
              <p style={citationMeta}>Editorial date: {retraction.citation.date} | Sport: {retraction.citation.sportsCovered.join(", ")}</p>
              <p style={citationMeta}>Measures: {retraction.citation.measurementIdentity}</p>
            </div>
            <p style={rowLabel}>Related reading</p>
            {retraction.relatedReading.map((reading) => (
              <p key={reading.sourceId} style={{ ...rowBody, marginTop: 3 }}>
                <Link href={resolveResearchSourceDestination(reading.sourceId).href} style={evidenceLink}>{reading.label}</Link>
              </p>
            ))}
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
