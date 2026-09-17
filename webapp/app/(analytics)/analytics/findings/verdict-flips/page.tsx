// Verdict Flip Anatomy -- a flagship honesty exhibit, sibling to
// findings/effective-sample-size (DESIGN Sec. 1 + 4 + 11). Narrates the claim
// families that changed their verdict as more data arrived -- the
// preregistered process working, not a failure -- plus the retracted-claim
// latency list. Server component, static export, no client JS -- reads the
// staged exhibit via loadArtifact() and renders every number verbatim.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { VerdictFlipCases, type VerdictFlipCase } from "@/components/analytics/verdict-flips/VerdictFlipCases";
import { findingMeta } from "@/lib/analytics/og";

import { FindingTableRegion } from "@/components/analytics/findings/FindingTableRegion";

import { FindingUnavailable } from "@/components/analytics/findings/FindingUnavailable";

export const metadata: Metadata = {
  title: "Verdict Flips",
  description:
    "Descriptive-only exhibit: the claim families that changed their verdict as more data arrived, and how long each retracted claim survived before it was caught.",
  ...findingMeta("verdict-flips"),
};

type Retracted = {
  sport: string; hypothesis: string; first_run_ts: string | null; last_run_ts: string | null;
  days_lived: number | null; n_history_rows: number; what_killed_it: string;
};
type Summary = { n_families: number; verified: number; null: number; retracted: number; not_testable: number; provisional: number };
type DatingCoverage = { n_history_rows_total: number; n_with_run_ts: number; note?: string };

type VerdictFlipAnatomy = Artifact & {
  headline?: string; summary?: Summary; flips?: VerdictFlipCase[];
  retracted?: Retracted[]; dating_coverage?: DatingCoverage; confounds?: string[];
};

const SPORT_LABEL: Record<string, string> = { basketball_nba: "NBA", mlb: "MLB", soccer_intl: "Soccer (Intl)", tennis: "Tennis" };
function sportLabel(sport: string): string {
  return SPORT_LABEL[sport] || sport.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function humanize(slug: string): string {
  const s = slug.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 16 };
const statLabel: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)" };
const statValue: CSSProperties = { fontSize: 26, color: "var(--ink)", marginTop: 2 };
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", whiteSpace: "nowrap" };
const td: CSSProperties = { fontSize: 14.5, color: "var(--ink)", padding: "12px 14px", borderBottom: "1px solid var(--rule)" };

export default function VerdictFlipsPage() {
  const data = loadArtifact("verdict_flip_anatomy") as VerdictFlipAnatomy | null;

  if (!data || !data.flips?.length) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Verdict flips</p>
        <h1 style={h1}>When we changed our mind</h1>
        <FindingUnavailable artifactId="verdict_flip_anatomy" />
      </div>
    );
  }

  const { headline, summary, flips, retracted, dating_coverage, confounds, source_artifact, generated_at } = data;
  const undatedRunCount = dating_coverage
    ? dating_coverage.n_history_rows_total - dating_coverage.n_with_run_ts
    : 0;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Verdict flips</p>
      <h1 style={h1}>When we changed our mind</h1>
      <p style={lede}>{headline}</p>

      {summary ? (
        <div className="tnum" style={{ display: "flex", flexWrap: "wrap", gap: 28, marginTop: 28, maxWidth: 700 }}>
          <div><div style={statLabel}>Claim families</div><div style={statValue}>{summary.n_families}</div></div>
          <div><div style={statLabel}>Verified</div><div style={statValue}>{summary.verified}</div></div>
          <div><div style={statLabel}>Null</div><div style={statValue}>{summary.null}</div></div>
          <div><div style={statLabel}>Retracted</div><div style={statValue}>{summary.retracted}</div></div>
        </div>
      ) : null}
      {summary ? (
        <p style={{ ...lede, fontSize: 13.5, color: "var(--ink-3)", marginTop: 10 }}>{flips.length} published examples changed verdict.</p>
      ) : null}

      <VerdictFlipCases flips={flips} generatedAt={generated_at || undefined} upstreamArtifact={source_artifact || ""} undatedRunCount={undatedRunCount} />

      {/* THE RETRACTED LATENCY LIST -- how long each caught claim survived. */}
      {retracted?.length ? (
        <>
          <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 40, marginBottom: 0, maxWidth: "none" }}>
            Retracted-claim latency
          </p>
          <FindingTableRegion label="Retracted-claim latency measurements" style={{ marginTop: 12, overflowX: "auto" }}>
            <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 640 }}>
              <thead>
                <tr>
                  <th style={th}>Claim</th>
                  <th style={th}>Sport</th>
                  <th style={th}>Days lived</th>
                  <th style={th}>What killed it</th>
                </tr>
              </thead>
              <tbody>
                {retracted.map((r) => (
                  <tr key={`${r.sport}-${r.hypothesis}`}>
                    <th scope="row" style={{ ...td, fontWeight: 600 }}>{humanize(r.hypothesis)}</th>
                    <td style={td}>{sportLabel(r.sport)}</td>
                    <td style={td}>{r.days_lived == null ? "undated" : r.days_lived}</td>
                    <td style={{ ...td, whiteSpace: "normal" }}>{r.what_killed_it}</td>
                  </tr>
                ))}
              </tbody>
            </table></FindingTableRegion>
          {dating_coverage ? (
            <p style={{ ...lede, fontSize: 13, color: "var(--ink-3)", marginTop: 10, maxWidth: "none" }}>
              run_ts present on {dating_coverage.n_with_run_ts} of {dating_coverage.n_history_rows_total} history rows
              {dating_coverage.note ? ` -- ${dating_coverage.note}` : ""}
            </p>
          ) : null}
        </>
      ) : null}

      {confounds?.length ? (
        <ul style={{ ...lede, fontSize: 14, color: "var(--ink-3)", marginTop: 28, paddingLeft: 18, maxWidth: 700 }}>
          {confounds.map((c, i) => (
            <li key={i} style={{ marginTop: i === 0 ? 0 : 6 }}>{c}</li>
          ))}
        </ul>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <Receipt sourceArtifact={source_artifact || ""} asOf={generated_at || undefined} dateKind="snapshot" label="descriptive_only" verdict="descriptive_only" />
      </div>
    </div>
  );
}
