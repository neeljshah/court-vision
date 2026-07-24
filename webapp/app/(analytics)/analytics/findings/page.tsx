// Findings index -- the hub for the honesty exhibits. Each findings page is a
// first-class editorial surface (retraction, effective sample size, verdict
// flips, MLB descriptive leaderboards); this list keeps every one reachable
// from the footer "Findings" link instead of leaving them as orphan URLs.
// Server component, static export, no client JS, ASCII only.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Findings",
  description:
    "Honesty exhibits (edge_claimed: false): retractions, effective sample size, verdict flips, and descriptive MLB leaderboards with their nulls attached.",
};

const BP = process.env.NEXT_PUBLIC_BASE_PATH || "";

// One entry per findings page. Descriptions say what the exhibit IS, plainly --
// these are the surfaces that make the honesty posture concrete, not marketing.
const FINDINGS: Array<{ href: string; title: string; blurb: string }> = [
  {
    href: "/analytics/findings/retraction",
    title: "Retractions",
    blurb:
      "The six numbers we took back, each with what it was, why it was wrong, and where it now lives only inside its retraction.",
  },
  {
    href: "/analytics/findings/effective-sample-size",
    title: "Effective sample size",
    blurb:
      "We deflate our own row counts: 78,986 within-game MLB rows carry the independent information of at most ~227 games, so confidence intervals must widen accordingly.",
  },
  {
    href: "/analytics/findings/verdict-flips",
    title: "Verdict flips",
    blurb:
      "The claim families that changed their mind as more data arrived -- each mind-change in sequence, plus how long the retracted claims lived. A flip is the process working.",
  },
  {
    href: "/analytics/findings/mlb-leaderboards",
    title: "MLB leaderboards, with the nulls",
    blurb:
      "Descriptive Statcast-derived leaderboards from a fixed 2022-2023 window, published beside the gate nulls that failed -- park factor too unstable to rank, umpire tendency does not move totals.",
  },
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
        These pages make the honest rail concrete. No dollar edge is claimed
        anywhere; each exhibit either takes a number apart, deflates our own
        sample, or publishes a result that failed &mdash; on purpose.
      </p>

      <div style={{ display: "grid", gap: 16, marginTop: 32, gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", maxWidth: 900 }}>
        {FINDINGS.map((f) => (
          <Link key={f.href} href={`${BP}${f.href}`} style={card}>
            <div className="serif" style={{ fontWeight: 500, fontSize: 21, color: "var(--ink)", marginBottom: 8 }}>
              {f.title}
            </div>
            <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)" }}>{f.blurb}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
