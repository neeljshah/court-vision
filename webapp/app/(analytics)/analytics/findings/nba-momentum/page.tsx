// NBA momentum: confirmed structural effects (fatigue, rest, clutch, timeout
// interrupts) vs null individual hot/cold carryover shapes -- direct analog of
// findings/tennis (same loadArtifact idiom, verdict-token coloring, claims
// table, confounds list, Receipt). Server component, static export, no client
// JS -- reads the staged exhibit at build time and renders every number
// verbatim, never recomputed. The only shape difference from tennis: the
// field is called `groups` here (2 of them), not `stories` (3).
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "NBA Momentum, Tested",
  description:
    "Descriptive-only exhibit (edge_claimed: false): confirmed NBA fatigue/rest/clutch effects vs null individual hot-cold carryover shapes.",
  ...findingMeta("nba-momentum"),
};

type Claim = {
  hypothesis: string;
  verdict: string;
  n: number;
  effect: number | null;
  corpus: string;
  reading: string;
};
type Group = { key: string; title: string; summary: string; claims: Claim[] };
type NbaMomentumTested = Artifact & {
  headline?: string;
  method?: string;
  groups?: Group[];
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

export default function NbaMomentumFindingsPage() {
  const data = loadArtifact("nba_momentum_tested") as NbaMomentumTested | null;

  if (!data || !data.groups?.length) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / NBA momentum</p>
        <h1 style={h1}>NBA momentum, tested: what&rsquo;s real and what isn&rsquo;t</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { headline, method, groups, confounds, source_artifact, generated_at } = data;

  const realGroup = groups.find((g) => g.key === "real") ?? groups[0];
  const nullGroup = groups.find((g) => g.key === "null") ?? groups[1];

  // The framing callout is built from the actual claims, never hardcoded: the
  // structural effect is the CONFIRMED_LOCAL fatigue/rest claim in the real
  // group; the contrast point is whichever null claim carries the largest n
  // (found by scanning, not named directly).
  const structuralClaim = realGroup?.claims.find(
    (c) => c.hypothesis.includes("rest_penalty") || c.hypothesis.includes("fatigue")
  );
  const biggestNull = nullGroup?.claims.reduce<Claim | undefined>(
    (max, c) => (max === undefined || c.n > max.n ? c : max),
    undefined
  );

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / NBA momentum</p>
      <h1 style={h1}>NBA momentum, tested: what&rsquo;s real and what isn&rsquo;t</h1>
      <p style={lede}>{headline}</p>
      {method ? <p style={{ ...lede, fontSize: 15, marginTop: 12 }}>{method}</p> : null}

      {groups.map((group) => (
        <div key={group.key} style={section}>
          <h2 className="serif" style={h2}>{group.title}</h2>
          <p style={{ ...lede, fontSize: 15, marginTop: 10, maxWidth: "none" }}>{group.summary}</p>

          {group.key === "null" && confounds?.[0] ? (
            <p style={{ ...callout, marginTop: 12 }}>{confounds[0]}</p>
          ) : null}

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
                {group.claims.map((c) => (
                  <tr key={c.hypothesis}>
                    <td style={{ ...td, fontWeight: 600, whiteSpace: "normal" }}>
                      {humanize(c.hypothesis)}
                      <span style={gloss}>{c.reading}</span>
                    </td>
                    <td style={td} className="mono">
                      <span style={{ color: verdictColor(c.verdict), fontWeight: 600 }}>{c.verdict}</span>
                    </td>
                    <td style={td}>{c.n.toLocaleString()}</td>
                    <td style={td}>{c.effect ?? "—"}</td>
                    <td style={{ ...td, color: "var(--ink-3)" }}>{c.corpus}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {structuralClaim && biggestNull ? (
        <p style={{ ...callout, maxWidth: 760 }}>
          <strong style={{ color: "var(--ink)" }}>How to read this &mdash; </strong>
          structural fatigue holds up ({humanize(structuralClaim.hypothesis)}, {structuralClaim.verdict} on n=
          {structuralClaim.n.toLocaleString()}, effect {structuralClaim.effect}), but the individual
          hot/cold carryover shape does not: even at n={biggestNull.n.toLocaleString()}, the largest
          sample in this whole exhibit, {humanize(biggestNull.hypothesis).toLowerCase()} comes back{" "}
          {biggestNull.verdict} &mdash; no signal past our baseline, not proof the shape never happens.
        </p>
      ) : null}

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
        with equal weight: a carryover shape that fails to show a signal is as
        valid a result as one that confirms.
      </p>
    </div>
  );
}
