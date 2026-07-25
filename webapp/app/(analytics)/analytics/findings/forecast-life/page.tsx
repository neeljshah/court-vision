// The life of a forecast -- traces how a betting market absorbs information
// twice: how the pre-game line finishes moving (novel_line_half_life), and how
// in-game accuracy sharpens as the game resolves (info_arrival_curve). Sibling
// to findings/reliability -- same honest conclusion (the market is ahead of
// us), just shown pregame and in-game instead of one snapshot. Server
// component, static export, no client JS -- reads the two staged exhibits via
// the shared loadArtifact() reader and renders every number verbatim, never
// recomputed, never re-rounded.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "The Life of a Forecast",
  description:
    "Descriptive-only exhibit (edge_claimed: false): how a betting market absorbs information pregame (line half-life) and in-game (Brier checkpoints) -- the market stays ahead of the model throughout, no dollar edge claimed.",
  ...findingMeta("forecast-life"),
};

type BoundaryFractions = { "6.0": number; "3.0": number; "1.0": number; "0.0": number };
type ObsWindow = { start: string; end: string; days: number; files: number };
type HalfLifeResult = {
  sport: string;
  half_life_label: string;
  final_hour_movement_share: number;
  cumulative_fraction_by_boundary_h: BoundaryFractions;
  n_move_pairs: number;
  observation_window: ObsWindow;
};
type HalfLifeArtifact = Artifact & {
  headline?: string;
  declared_confounds?: string[];
  results?: HalfLifeResult[];
};

type Checkpoint = { n: number; model_brier: number; market_brier: number; naive_brier: number; market_minus_model_brier: number };
type ArrivalArtifact = Artifact & {
  checkpoints?: Record<string, Record<string, Checkpoint>>;
};

const SPORT_LABEL: Record<string, string> = { mlb: "MLB", soccer_intl: "Soccer (Intl)", nba: "NBA", tennis: "Tennis", wnba: "WNBA" };
function sportLabel(sport: string): string {
  return SPORT_LABEL[sport] || sport.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 720, marginTop: 16 };
const sectionH: CSSProperties = { ...lede, fontSize: 21, fontWeight: 600, color: "var(--ink)", marginTop: 40, maxWidth: 760 };
const standfirst: CSSProperties = { ...lede, fontSize: 15.5, maxWidth: 760, marginTop: 8, fontStyle: "italic" };
const headlineBox: CSSProperties = { marginTop: 16, padding: "16px 20px", background: "var(--paper-tint)", borderLeft: "3px solid var(--accent)", borderRadius: "var(--radius-card)", maxWidth: 760, fontSize: 16, fontWeight: 600, color: "var(--ink)", lineHeight: 1.55 };
const windowChip: CSSProperties = { marginTop: 12, display: "inline-block", padding: "8px 14px", background: "var(--paper-tint)", border: "1px solid var(--rule-strong)", borderRadius: "var(--radius-chip)", fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 };
const noteBox: CSSProperties = { marginTop: 16, padding: "14px 18px", background: "var(--paper-tint)", borderLeft: "2px solid var(--rule-strong)", borderRadius: "var(--radius-card)", maxWidth: 760, fontSize: 14, color: "var(--ink-2)", lineHeight: 1.6 };
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", whiteSpace: "nowrap" };
const td: CSSProperties = { fontSize: 14.5, color: "var(--ink)", padding: "10px 14px", borderBottom: "1px solid var(--rule)", whiteSpace: "nowrap" };
const tableWrap: CSSProperties = { marginTop: 16, overflowX: "auto", maxWidth: 900 };
const confoundList: CSSProperties = { marginTop: 12, paddingLeft: 20, maxWidth: 760, fontSize: 14, lineHeight: 1.7, color: "var(--ink-3)" };

export default function ForecastLifePage() {
  const halfLife = loadArtifact("novel_line_half_life") as HalfLifeArtifact | null;
  const arrival = loadArtifact("info_arrival_curve") as ArrivalArtifact | null;
  const results = halfLife?.results || [];
  const checkpoints = arrival?.checkpoints || {};

  if (!halfLife || results.length === 0 || !arrival || Object.keys(checkpoints).length === 0) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Life of a forecast</p>
        <h1 style={h1}>The life of a forecast</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  // Observation window: derived from the results' own per-sport windows, not
  // hardcoded -- min start / max end across whichever sports the artifact ships.
  const starts = results.map((r) => r.observation_window.start);
  const ends = results.map((r) => r.observation_window.end);
  const winStart = starts.reduce((a, b) => (b < a ? b : a));
  const winEnd = ends.reduce((a, b) => (b > a ? b : a));
  const winDays = Math.round((Date.parse(winEnd) - Date.parse(winStart)) / 86400000) + 1;

  const inGameSports = ["mlb", "soccer_intl"].filter((s) => checkpoints[s]);

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Life of a forecast</p>
      <h1 style={h1}>The life of a forecast</h1>
      <p style={lede}>
        A betting market absorbs information continuously, not all at once. This traces that process twice: how the
        pre-game line finishes moving before tip, and how in-game accuracy sharpens as the game resolves toward its
        outcome. No dollar edge is claimed anywhere on this page.
      </p>

      <p style={sectionH}>Before tip: when the line stops moving</p>
      {halfLife.headline ? <p style={standfirst}>{halfLife.headline}</p> : null}
      <p style={windowChip}>
        Move-pair counts are dense samples inside a ~{winDays}-day line-history window ({winStart} to {winEnd}), not a
        season.
      </p>

      <div style={tableWrap}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 640 }}>
          <thead>
            <tr>
              <th style={th}>Sport</th>
              <th style={th}>Half-life (h)</th>
              <th style={th}>Frac. by 6h</th>
              <th style={th}>by 3h</th>
              <th style={th}>by 1h</th>
              <th style={th}>Final-hour share</th>
              <th style={th}>Move-pairs</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.sport}>
                <td style={{ ...td, fontWeight: 600 }}>{sportLabel(r.sport)}</td>
                <td style={td} className="mono">{r.half_life_label}</td>
                <td style={td} className="mono">{r.cumulative_fraction_by_boundary_h["6.0"]}</td>
                <td style={td} className="mono">{r.cumulative_fraction_by_boundary_h["3.0"]}</td>
                <td style={td} className="mono">{r.cumulative_fraction_by_boundary_h["1.0"]}</td>
                <td style={td} className="mono">{r.final_hour_movement_share}</td>
                <td style={td} className="mono">{r.n_move_pairs.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ ...standfirst, fontStyle: "normal", fontSize: 13, color: "var(--ink-3)" }}>
        Fractions are cumulative share of total absolute line motion completed by that many hours before tip (0..1, not a percent).
      </p>

      <p style={sectionH}>During the game: when the forecast sharpens</p>
      <p style={headlineBox}>
        The honest headline: the market&apos;s Brier score falls steadily as each game resolves, and stays BELOW the
        model&apos;s the whole way -- market_minus_model_brier is negative at every checkpoint shown here. The market
        is ahead of us throughout the game, not just at the opening line. See{" "}
        <Link href="/analytics/findings/reliability" style={{ color: "var(--accent)", fontWeight: 600 }}>
          reliability
        </Link>{" "}
        for the same story pregame.
      </p>

      {inGameSports.map((sport) => (
        <div key={sport} style={{ marginTop: 28 }}>
          <p style={{ ...sectionH, fontSize: 16, marginTop: 0, fontWeight: 700 }}>{sportLabel(sport)}</p>
          <div style={tableWrap}>
            <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 560 }}>
              <thead>
                <tr>
                  <th style={th}>Checkpoint</th>
                  <th style={th}>n</th>
                  <th style={th}>Market Brier</th>
                  <th style={th}>Model Brier</th>
                  <th style={th}>Naive Brier</th>
                  <th style={th}>Market - Model</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(checkpoints[sport]).map(([key, c]) => (
                  <tr key={key}>
                    <td style={{ ...td, fontWeight: 600 }} className="mono">{key}</td>
                    <td style={td} className="mono">{c.n.toLocaleString()}</td>
                    <td style={td} className="mono">{c.market_brier}</td>
                    <td style={td} className="mono">{c.model_brier}</td>
                    <td style={td} className="mono">{c.naive_brier}</td>
                    <td style={td} className="mono">{c.market_minus_model_brier}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <div style={{ marginTop: 24, maxWidth: 760 }}>
        <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 0, marginBottom: 8 }}>
          Confounds / notes
        </p>
        <ul style={confoundList}>
          {(halfLife.declared_confounds || []).map((c, i) => <li key={i}>{c}</li>)}
          <li>In-game checkpoints are per-inning (MLB) or per-5-minute-bucket (soccer) Brier on modest n in the late buckets -- e.g. MLB checkpoint 11 has n=18 -- so late-game values above are noisy, not a smooth trend.</li>
          <li>Everything on this page is descriptive: no edge or ROI claim is made anywhere.</li>
        </ul>
      </div>

      <div style={{ marginTop: 20, display: "flex", flexWrap: "wrap", gap: 16 }}>
        <Receipt
          sourceArtifact="scripts/platformkit/analytics_showcase/out/novel_line_half_life.json"
          asOf={halfLife.as_of || halfLife.generated_at || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
        <Receipt
          sourceArtifact="scripts/platformkit/analytics_showcase/out/info_arrival_curve.json"
          asOf={arrival.as_of || arrival.generated_at || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        The whole product sits on this: the market is efficient, we aim to match the close, and the honest edge we
        claim is calibration -- not dollars.
      </p>
    </div>
  );
}
