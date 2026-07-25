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
  {
    href: "/analytics/findings/tennis",
    title: "Tennis: momentum's grain limit",
    blurb:
      "Momentum is real point-to-point (n=456,383, confirmed) but dies at the game grain; two tiebreak myths come back null; altitude and travel effects are confirmed, altitude replicated across two disjoint year slices.",
  },
  {
    href: "/analytics/findings/nba-momentum",
    title: "NBA momentum, tested",
    blurb:
      "The honest split: structural fatigue, rest, and clutch effects are confirmed and some replicated, while the individual hot/cold carryover shapes -- even a player's own B2B dip at n=65,103 -- come back null.",
  },
  {
    href: "/analytics/findings/q4-shift",
    title: "The fourth-quarter shift",
    blurb:
      "The module that honestly refused a clutch number, turned into a descriptive one: per-player Q4-vs-earlier per-36 shifts over 1,231 games -- published with the blowout/garbage-time confound in plain sight, never as a clutch or predictive claim.",
  },
  {
    href: "/analytics/findings/shrinkage",
    title: "When the leaderboard regresses",
    blurb:
      "Empirical-Bayes shrinkage on the MLB rate leaderboards: small-sample 'leaders' get pulled toward the group mean by how few trials back them, while a huge-sample rate barely moves. The raw-vs-shrunk gap is the honesty.",
  },
  {
    href: "/analytics/findings/reliability",
    title: "Are our probabilities honest?",
    blurb:
      "Calibration reliability diagrams and the Murphy Brier decomposition: our model's Brier trails the market's (0.2377 vs 0.2067 in MLB), and the gap is resolution -- information we don't have -- not miscalibration. We match or trail the close; we never claim to beat it.",
  },
  {
    href: "/analytics/findings/forecast-life",
    title: "The life of a forecast",
    blurb:
      "How a market absorbs information, twice: pre-game line half-life per sport, then in-game Brier checkpoints where the market stays ahead of our model at every point measured. Descriptive only, same honest gap as reliability.",
  },
  {
    href: "/analytics/findings/soccer-home-advantage",
    title: "Home advantage, decomposed",
    blurb:
      "49,425 international matches split on the real neutral-site flag: the true-home/neutral goal-diff gap grew from 0.22 to 0.50 not because true-home advantage rose (flat) but because the neutral-venue edge collapsed over time.",
  },
  {
    href: "/analytics/findings/bookmaker-accuracy",
    title: "We graded the bookmakers",
    blurb:
      "Proportional-devig Brier on shared-game subsets: Pinnacle is barely the sharpest book on tennis match-winner (0.1975 vs Bet365's 0.1980), while on soccer over/under 2.5 goals the books are a statistical dead heat.",
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
