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

export const metadata: Metadata = {
  title: "Verdict Flips",
  description:
    "Descriptive-only exhibit (edge_claimed: false): the claim families that changed their verdict as more data arrived, and how long each retracted claim survived before it was caught.",
};

type Step = { verdict: string; status: string; corpus: string; n: number; effect: number | string; run_ts: string | null };
type Flip = { sport: string; hypothesis: string; current_status: string; verdict_sequence: string[]; steps: Step[]; one_line: string };
type Retracted = {
  sport: string; hypothesis: string; first_run_ts: string | null; last_run_ts: string | null;
  days_lived: number | null; n_history_rows: number; what_killed_it: string;
};
type Summary = { n_families: number; verified: number; null: number; retracted: number; not_testable: number; provisional: number };
type DatingCoverage = { n_history_rows_total: number; n_with_run_ts: number; note?: string };

type VerdictFlipAnatomy = Artifact & {
  headline?: string; method?: string; summary?: Summary; flips?: Flip[];
  retracted?: Retracted[]; dating_coverage?: DatingCoverage; confounds?: string[];
};

const SPORT_LABEL: Record<string, string> = { basketball_nba: "NBA", mlb: "MLB", soccer_intl: "Soccer (Intl)", tennis: "Tennis" };
function sportLabel(sport: string): string {
  return SPORT_LABEL[sport] || sport.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
// Lightly humanize a hypothesis slug for prose -- underscores to spaces,
// first letter capitalized. Never touches the words, so meaning can't drift.
function humanize(slug: string): string {
  const s = slug.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
// Final arrow-chain token gets a tasteful nod to its status; everything else
// (and any non-confirmed final token) stays muted -- no loud red/green.
function tokenColor(token: string): string {
  const t = token.toUpperCase();
  return t.includes("CONFIRMED") || t.includes("VERIFIED") ? "var(--accent)" : "var(--ink-3)";
}

const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 16 };
const statLabel: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)" };
const statValue: CSSProperties = { fontSize: 26, color: "var(--ink)", marginTop: 2 };
const card: CSSProperties = { marginTop: 20, padding: "18px 20px", background: "var(--paper-raised)", border: "1px solid var(--rule)", borderRadius: "var(--radius-card)", maxWidth: 700 };
const sportTag: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", border: "1px solid var(--rule-strong)", borderRadius: "var(--radius-chip)", padding: "2px 8px", display: "inline-block" };
const stepsBox: CSSProperties = { marginTop: 12, padding: "10px 14px", background: "var(--paper-tint)", border: "1px solid var(--rule)", borderRadius: "var(--radius-card)" };
const stepRow: CSSProperties = { fontSize: 13, color: "var(--ink-2)", padding: "5px 0", borderBottom: "1px solid var(--rule)" };
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", whiteSpace: "nowrap" };
const td: CSSProperties = { fontSize: 14.5, color: "var(--ink)", padding: "12px 14px", borderBottom: "1px solid var(--rule)" };

export default function VerdictFlipsPage() {
  const data = loadArtifact("verdict_flip_anatomy") as VerdictFlipAnatomy | null;

  if (!data || !data.flips?.length) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Verdict flips</p>
        <h1 style={h1}>When we changed our mind</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { headline, method, summary, flips, retracted, dating_coverage, confounds, source_artifact, generated_at } = data;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Verdict flips</p>
      <h1 style={h1}>When we changed our mind</h1>
      <p style={lede}>{headline}</p>
      {method ? <p style={{ ...lede, fontSize: 15, marginTop: 12 }}>{method}</p> : null}

      {summary ? (
        <div className="tnum" style={{ display: "flex", flexWrap: "wrap", gap: 28, marginTop: 28, maxWidth: 700 }}>
          <div><div style={statLabel}>Claim families</div><div style={statValue}>{summary.n_families}</div></div>
          <div><div style={statLabel}>Verified</div><div style={statValue}>{summary.verified}</div></div>
          <div><div style={statLabel}>Null</div><div style={statValue}>{summary.null}</div></div>
          <div><div style={statLabel}>Retracted</div><div style={statValue}>{summary.retracted}</div></div>
        </div>
      ) : null}
      {summary ? (
        <p style={{ ...lede, fontSize: 13.5, color: "var(--ink-3)", marginTop: 10 }}>Most claims never flip; these few did.</p>
      ) : null}

      {/* THE FLIPS -- one card per claim family, in the sequence it actually lived. */}
      {(flips ?? []).map((f) => (
        <div key={`${f.sport}-${f.hypothesis}`} style={card}>
          <span style={sportTag}>{sportLabel(f.sport)}</span>
          <h3 className="serif" style={{ fontSize: 19, fontWeight: 500, color: "var(--ink)", marginTop: 10 }}>
            {humanize(f.hypothesis)}
          </h3>
          <p className="mono" style={{ fontSize: 13.5, marginTop: 8, color: "var(--ink-3)" }}>
            {f.verdict_sequence.map((token, i) => (
              <span key={i}>
                {i > 0 ? <span style={{ margin: "0 6px" }}>&#8594;</span> : null}
                <span style={i === f.verdict_sequence.length - 1 ? { color: tokenColor(token), fontWeight: 600 } : undefined}>
                  {token}
                </span>
              </span>
            ))}
          </p>
          <p style={{ ...lede, fontSize: 15, marginTop: 10, maxWidth: "none" }}>{f.one_line}</p>
          <div style={stepsBox}>
            {f.steps.map((s, i) => (
              <div key={i} style={{ ...stepRow, borderBottom: i === f.steps.length - 1 ? "none" : stepRow.borderBottom }}>
                <span style={{ fontWeight: 600, color: "var(--ink)" }}>Step {i + 1}</span>
                {" -- "}
                <span className="mono">{s.verdict}</span> on {s.corpus}, n={s.n}, effect {s.effect}
                {" ("}
                {s.run_ts ? <span className="mono tnum">{s.run_ts}</span> : "undated"}
                {")"}
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* THE RETRACTED LATENCY LIST -- how long each caught claim survived. */}
      {retracted?.length ? (
        <>
          <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 40, marginBottom: 0, maxWidth: "none" }}>
            Retracted-claim latency
          </p>
          <div style={{ marginTop: 12, overflowX: "auto" }}>
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
                    <td style={{ ...td, fontWeight: 600 }}>{humanize(r.hypothesis)}</td>
                    <td style={td}>{sportLabel(r.sport)}</td>
                    <td style={td}>{r.days_lived == null ? "undated" : r.days_lived}</td>
                    <td style={{ ...td, whiteSpace: "normal" }}>{r.what_killed_it}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
        <Receipt sourceArtifact={source_artifact || ""} asOf={generated_at || undefined} label="descriptive_only" verdict="descriptive_only" />
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        A verdict flip is the preregistered process working, not a failure &mdash; no
        edge or ROI is claimed anywhere on this page.
      </p>
    </div>
  );
}
