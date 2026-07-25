// Tennis: grain limit + null myths + confirmed altitude/travel -- a curated
// findings exhibit, sibling to findings/verdict-flips and
// findings/effective-sample-size (same loadArtifact idiom, CSSProperties style
// objects, verdict-token coloring, confounds list, Receipt). Server component,
// static export, no client JS -- reads the staged exhibit at build time and
// renders every number verbatim, never recomputed.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "Tennis: Momentum, Myths, and Altitude",
  description:
    "Descriptive-only exhibit (edge_claimed: false): momentum's grain limit, two null tiebreak myths, and confirmed altitude/travel effects in tennis.",
  ...findingMeta("tennis"),
};

type Claim = {
  hypothesis: string;
  verdict: string;
  n: number;
  effect: number;
  corpus: string;
  reading: string;
};
type Story = { key: string; title: string; summary: string; claims: Claim[] };
type TennisGrainAndMyths = Artifact & {
  headline?: string;
  method?: string;
  stories?: Story[];
  confounds?: string[];
};

// Lightly humanize a hypothesis slug for prose -- underscores to spaces, first
// letter capitalized. Never touches the words, so meaning can't drift.
function humanize(slug: string): string {
  const s = slug.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
// CONFIRMED_LOCAL / REPLICATED get the accent tone; NULL_LOCAL (and anything
// else) stays muted -- null is a neutral, first-class result, never red.
function verdictColor(v: string): string {
  const t = v.toUpperCase();
  return t.includes("CONFIRMED") || t.includes("REPLICATED") ? "var(--accent)" : "var(--ink-3)";
}

const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 16 };
const h2: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 22, color: "var(--ink)", marginTop: 0 };
const section: CSSProperties = { marginTop: 36, maxWidth: 760 };
const callout: CSSProperties = { marginTop: 16, padding: "14px 18px", background: "var(--paper-tint)", borderLeft: "2px solid var(--rule-strong)", borderRadius: "var(--radius-card)", maxWidth: 700, fontSize: 14, color: "var(--ink-2)", lineHeight: 1.6 };
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", whiteSpace: "nowrap" };
const td: CSSProperties = { fontSize: 14.5, color: "var(--ink)", padding: "12px 14px", borderBottom: "1px solid var(--rule)", verticalAlign: "top" };
const gloss: CSSProperties = { display: "block", fontSize: 12.5, color: "var(--ink-3)", marginTop: 3, whiteSpace: "normal" };

export default function TennisFindingsPage() {
  const data = loadArtifact("tennis_grain_and_myths") as TennisGrainAndMyths | null;

  if (!data || !data.stories?.length) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Tennis</p>
        <h1 style={h1}>Tennis: where momentum lives, and where it doesn&rsquo;t</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { headline, method, stories, confounds, source_artifact, generated_at } = data;

  // Story 1's framing callout is built from its own claims, never hardcoded:
  // the point-grain claim is the CONFIRMED_LOCAL one; the game-grain claim is
  // the base post-break-hold NULL_LOCAL one (not a split-half variant).
  const momentumStory = stories[0];
  const pointClaim = momentumStory?.claims.find((c) => c.verdict.toUpperCase().includes("CONFIRMED"));
  const gameClaim = momentumStory?.claims.find(
    (c) => c.verdict.toUpperCase().includes("NULL") && !c.hypothesis.includes("split")
  );

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Tennis</p>
      <h1 style={h1}>Tennis: where momentum lives, and where it doesn&rsquo;t</h1>
      <p style={lede}>{headline}</p>
      {method ? <p style={{ ...lede, fontSize: 15, marginTop: 12 }}>{method}</p> : null}

      {stories.map((story, si) => (
        <div key={story.key} style={section}>
          <h2 className="serif" style={h2}>{story.title}</h2>
          <p style={{ ...lede, fontSize: 15, marginTop: 10, maxWidth: "none" }}>{story.summary}</p>

          <div style={{ marginTop: 16, overflowX: "auto" }}>
            <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}>
              <thead>
                <tr>
                  <th style={th}>Claim</th>
                  <th style={th}>Verdict</th>
                  <th style={th}>n</th>
                  <th style={th}>Effect</th>
                  <th style={th}>Corpus</th>
                </tr>
              </thead>
              <tbody>
                {story.claims.map((c) => (
                  <tr key={c.hypothesis}>
                    <td style={{ ...td, fontWeight: 600, whiteSpace: "normal" }}>
                      {humanize(c.hypothesis)}
                      <span style={gloss}>{c.reading}</span>
                    </td>
                    <td style={td} className="mono">
                      <span style={{ color: verdictColor(c.verdict), fontWeight: 600 }}>{c.verdict}</span>
                    </td>
                    <td style={td}>{c.n.toLocaleString()}</td>
                    <td style={td}>{c.effect}</td>
                    <td style={{ ...td, color: "var(--ink-3)" }}>{c.corpus}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {si === 0 && pointClaim && gameClaim ? (
            <p style={callout}>
              <strong style={{ color: "var(--ink)" }}>How to read this &mdash; </strong>
              momentum is real point-to-point ({pointClaim.verdict} on n=
              {pointClaim.n.toLocaleString()}) but goes null the moment you zoom out to the
              game grain (post-break hold rate, {gameClaim.verdict} on n=
              {gameClaim.n.toLocaleString()}). Same idea, different grain, opposite verdict.
            </p>
          ) : null}
        </div>
      ))}

      {confounds?.length ? (
        <ul style={{ ...lede, fontSize: 14, color: "var(--ink-3)", marginTop: 32, paddingLeft: 18, maxWidth: 700 }}>
          {confounds.map((c, i) => (
            <li key={i} style={{ marginTop: i === 0 ? 0 : 6 }}>{c}</li>
          ))}
        </ul>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <Receipt sourceArtifact={source_artifact || ""} asOf={generated_at || undefined} label="descriptive_only" verdict="descriptive_only" />
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        CONFIRMED here means a leak-free accuracy/effect finding against our own
        baseline &mdash; never a betting edge or ROI claim. Nulls are published
        with equal weight: a myth that fails to show an effect is as valid a
        result as one that confirms.
      </p>
    </div>
  );
}
