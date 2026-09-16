// Findings index -- the hub for the honesty exhibits. Each findings page is a
// first-class editorial surface (retraction, effective sample size, verdict
// flips, MLB descriptive leaderboards); this list keeps every one reachable
// from the footer "Findings" link instead of leaving them as orphan URLs.
// Server component, static export, no client JS, ASCII only.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { findingsIndex } from "@/lib/analytics/findingsIndex";

export const metadata: Metadata = {
  title: "Findings",
  description:
    "Dated descriptive exhibits: retractions, effective sample size, verdict flips, and MLB leaderboards linked to published source artifacts.",
};


// One entry per findings page. Descriptions say what the exhibit IS, plainly --
// these are the surfaces that make the honesty posture concrete, not marketing.

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
  maxWidth: 720,
  marginTop: 16,
};
const card: CSSProperties = {
  display: "block",
  padding: "20px 22px",
  background: "var(--paper-raised)",
  border: "1px solid var(--rule)",
  borderRadius: "var(--radius-card)",
  boxShadow: "var(--shadow-card)",
};

export default function FindingsIndexPage() {
  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings</p>
      <h1 style={h1}>The honesty exhibits</h1>
      <p style={lede}>
        These pages document how measurements hold up under review. Each exhibit
        either takes a number apart, deflates its own sample, or publishes a
        failed result alongside the dated source artifact.
      </p>

      <div style={{ display: "grid", gap: 16, marginTop: 32, gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", maxWidth: 900 }}>
        {findingsIndex.map((f) => (
          // prefetch={false}: static export has no RSC prefetch payload, so the
          // default hover/viewport prefetch only 404s -- disable it on these cards.
          <Link key={f.slug} href={`/analytics/findings/${f.slug}/`} style={card} prefetch={false}>
            <div className="serif" style={{ fontWeight: 500, fontSize: 21, color: "var(--ink)", marginBottom: 8 }}>
              {f.title}
            </div>
            <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)" }}>{f.dek}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
