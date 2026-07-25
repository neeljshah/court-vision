// Effective Sample Size -- a flagship honesty exhibit, sibling to
// findings/retraction (DESIGN Sec. 1 + 4 + 11). Where retraction/page.tsx takes
// apart six PUBLISHED numbers, this page takes apart our OWN row counts: it
// shows that within-game rows are near-duplicates (the outcome is fixed, the
// win-probability path is smooth) and states, per corpus, how few INDEPENDENT
// games those rows are actually worth. Server component, static export, no
// client JS -- reads the staged exhibit at build time via the shared
// loadArtifact() reader (same missing-file-safe try/catch every showcase page
// uses) and renders every number verbatim, never recomputed, never re-rounded.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "Effective Sample Size",
  description:
    "Descriptive-only exhibit (edge_claimed: false): within-game rows are near-duplicates, so this table deflates our own sample sizes down to the honest, independent-game count.",
  ...findingMeta("effective-sample-size"),
};

type Corpus = {
  sport: string;
  n_rows: number;
  n_games: number;
  rho_model: number;
  rho_market: number;
  ess_ar1: number;
  ess_anchor: number;
  infl_ar1: number;
  infl_anchor: number;
};

type EssLedger = Artifact & {
  headline?: string;
  method?: string;
  formula?: string;
  confound?: string;
  corpora?: Corpus[];
};

const SPORT_LABEL: Record<string, string> = {
  mlb: "MLB",
  soccer_intl: "Soccer (Intl)",
};
function sportLabel(sport: string): string {
  return SPORT_LABEL[sport] || sport.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

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
  maxWidth: 700,
  marginTop: 16,
};
const noteBox: CSSProperties = {
  marginTop: 28,
  padding: "14px 18px",
  background: "var(--paper-tint)",
  borderLeft: "2px solid var(--rule-strong)",
  borderRadius: "var(--radius-card)",
  maxWidth: 700,
  fontSize: 14,
  color: "var(--ink-2)",
  lineHeight: 1.6,
};
const th: CSSProperties = {
  textAlign: "left",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--ink-3)",
  padding: "8px 14px",
  borderBottom: "1px solid var(--rule-strong)",
  whiteSpace: "nowrap",
};
const td: CSSProperties = {
  fontSize: 14.5,
  color: "var(--ink)",
  padding: "12px 14px",
  borderBottom: "1px solid var(--rule)",
  whiteSpace: "nowrap",
};
const tdSub: CSSProperties = { display: "block", fontSize: 11.5, color: "var(--ink-3)", marginTop: 2 };
const formulaBlock: CSSProperties = {
  marginTop: 12,
  padding: "14px 16px",
  background: "var(--paper-raised)",
  border: "1px solid var(--rule)",
  borderRadius: "var(--radius-card)",
  maxWidth: 700,
  fontSize: 13,
  color: "var(--ink-2)",
  lineHeight: 1.6,
  whiteSpace: "pre-wrap",
};

export default function EffectiveSampleSizePage() {
  const data = loadArtifact("ess_ledger") as EssLedger | null;

  if (!data || !data.corpora?.length) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Effective Sample Size</p>
        <h1 style={h1}>How independent is our data, really?</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { headline, method, formula, confound, source_artifact, generated_at, corpora } = data;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Effective Sample Size</p>
      <h1 style={h1}>How independent is our data, really?</h1>
      <p style={lede}>{headline}</p>
      {method ? <p style={{ ...lede, fontSize: 15, marginTop: 12 }}>{method}</p> : null}

      <div style={{ marginTop: 24, overflowX: "auto", maxWidth: 700 }}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}>
          <thead>
            <tr>
              <th style={th}>Corpus</th>
              <th style={th}>Rows</th>
              <th style={th}>Distinct games</th>
              <th style={th}>Residual autocorr (rho)</th>
              <th style={th}>Effective sample (AR1)</th>
              <th style={th}>Honest anchor</th>
              <th style={th}>CI must widen by</th>
            </tr>
          </thead>
          <tbody>
            {corpora.map((c) => (
              <tr key={c.sport}>
                <td style={{ ...td, fontWeight: 600 }}>{sportLabel(c.sport)}</td>
                <td style={td}>{c.n_rows.toLocaleString()}</td>
                <td style={td}>{c.n_games.toLocaleString()}</td>
                <td style={td} className="mono">
                  {c.rho_model.toFixed(4)}
                  <span style={tdSub}>market {c.rho_market.toFixed(4)}</span>
                </td>
                <td style={td}>{c.ess_ar1.toLocaleString()}</td>
                <td style={td}>{c.ess_anchor.toLocaleString()}</td>
                <td style={{ ...td, fontWeight: 600 }}>
                  {c.infl_anchor}x
                  <span style={tdSub}>AR1 estimate {c.infl_ar1}x</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* The lead example is templated off corpora[0], never hardcoded: on a page
          whose entire point is number integrity, a prose "78,986 -> 227" that could
          drift from the table it explains would be exactly the failure this exhibit
          exists to prevent. */}
      <p style={{ ...noteBox, marginTop: 24 }}>
        <strong style={{ color: "var(--ink)" }}>How to read this &mdash; </strong>
        rows within one game are near-duplicates because the outcome is fixed and the
        win-probability path is smooth, so {corpora[0].n_rows.toLocaleString()}{" "}
        {sportLabel(corpora[0].sport)} rows carry the independent information of at
        most ~{corpora[0].ess_anchor.toLocaleString()} games. Every confidence
        interval on a within-game analysis must therefore be widened by the factor in
        the last column.
      </p>

      {formula ? (
        <>
          <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 24, marginBottom: 0 }}>
            Formula
          </p>
          <div className="mono" style={formulaBlock}>{formula}</div>
        </>
      ) : null}

      {confound ? <p style={{ ...lede, fontSize: 14, color: "var(--ink-3)", marginTop: 20 }}>{confound}</p> : null}

      <div style={{ marginTop: 16 }}>
        <Receipt
          sourceArtifact={source_artifact || ""}
          asOf={generated_at || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        This exhibit deflates our own numbers on purpose &mdash; no edge or ROI is
        claimed anywhere here, only the honest count of what was actually
        measured.
      </p>
    </div>
  );
}
