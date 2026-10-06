// Historical joined-corpus ESS ledger. Its stored-series count was published
// as n_games but does not verify distinct games; all numerical values below
// remain the original snapshot and are interpreted as proxies.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

import { FindingTableRegion } from "@/components/analytics/findings/FindingTableRegion";

import { FindingUnavailable } from "@/components/analytics/findings/FindingUnavailable";
import { DataIntegrityNotice } from "@/components/analytics/DataIntegrityNotice";
import { noticesForModules } from "@/lib/analytics/dataIntegrity";

export const metadata: Metadata = {
  title: "Effective Sample Size",
  description:
    "Descriptive-only historical AR(1) proxy and stored-series anchor for joined-corpus rows; distinct games and intervals await recomposition.",
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
  formula?: string;
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

const LEDGER_ID = "ess_ledger";

export default function EffectiveSampleSizePage() {
  const data = loadArtifact(LEDGER_ID) as EssLedger | null;

  if (!data || !data.corpora?.length) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Effective Sample Size</p>
        <h1 style={h1}>How independent is our data, really?</h1>
        <FindingUnavailable artifactId={LEDGER_ID} />
      </div>
    );
  }

  const { formula, generated_at, corpora } = data;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Effective Sample Size</p>
      <h1 style={h1}>How independent is our data, really?</h1>
      <p style={lede}>
        This historical ledger estimates row dependence with lag-1 residual autocorrelation.
        Its published anchor is a proxy, not a verified count of distinct games.
      </p>
      <DataIntegrityNotice notices={noticesForModules([LEDGER_ID])} moduleIds={[LEDGER_ID]} />
      <p style={{ ...lede, fontSize: 15, marginTop: 12 }}>
        Support label: this ledger is the joined-corpus measurement, revision 1. It was taken
        on the MLB and international soccer in-game corpus before that corpus was re-segmented
        into one stored file per game, and its recomposition on the segment-clean corpus is
        pending, so every row below describes the joined corpus rather than the published
        revision 2 population.
      </p>
      <p style={{ ...lede, fontSize: 15, marginTop: 12 }}>
        The AR(1) estimate approximates effective rows from the recorded residual rho.
        The published anchor takes min(AR(1) estimate, stored series count). The
        stored series field counts (game_id, side) pairs. Multiple sides and mixed-game
        input paths mean this count cannot establish how many distinct games were observed.
      </p>

      <FindingTableRegion label="Published measurements" style={{ marginTop: 24, overflowX: "auto", maxWidth: 700 }}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}>
          <thead>
            <tr>
              <th style={th}>Corpus</th>
              <th style={th}>Rows</th>
              <th style={th}>Stored series</th>
              <th style={th}>Residual autocorr (rho)</th>
              <th style={th}>Effective sample (AR1 proxy)</th>
              <th style={th}>Published anchor (proxy)</th>
              <th style={th}>Implied interval-width factor</th>
            </tr>
          </thead>
          <tbody>
            {corpora.map((c) => (
              <tr key={c.sport}>
                <th scope="row" style={{ ...td, fontWeight: 600 }}>{sportLabel(c.sport)}</th>
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
        </table></FindingTableRegion>

      {/* Keep the historical example tied to the displayed snapshot values. */}
      <p style={{ ...noteBox, marginTop: 24 }}>
        <strong style={{ color: "var(--ink)" }}>How to read this &mdash; </strong>
        the historical {sportLabel(corpora[0].sport)} snapshot has{" "}
        {corpora[0].n_rows.toLocaleString()} rows and a published anchor proxy of{" "}
        {corpora[0].ess_anchor.toLocaleString()}, capped by the stored series count.
        The last column is an implied interval-width factor under that proxy; it is
        not an instruction to scale a published interval. Intervals on the
        regenerated corpus are re-estimated by cluster bootstrap, never widened from
        an earlier number.
      </p>

      {formula ? (
        <>
          <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 24, marginBottom: 0 }}>
            Formula
          </p>
          <div className="mono" style={formulaBlock}>{formula}</div>
        </>
      ) : null}

      <p style={{ ...lede, fontSize: 14, color: "var(--ink-3)", marginTop: 20 }}>
        AR(1) is a first-order approximation of a smooth residual path, not a full
        independence model. This descriptive-only snapshot makes no advantage or return claim.
      </p>

      <div style={{ marginTop: 16 }}>
        <Receipt
          sourceArtifact="webapp/public/data/showcase/ess_ledger.json"
          asOf={generated_at || undefined}
          dateKind="snapshot"
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        These historical proxy values describe the joined corpus only. Distinct-game
        counts and replacement intervals require the pending segment-clean recomposition.
      </p>
    </div>
  );
}
