// Soccer home-advantage decomposition -- venue vs neutral, via the neutral-site
// control. Home advantage is real, and the true-home/neutral gap GREW over
// time, but not because true-home edge rose (it is flat) -- it grew because
// the neutral-venue edge COLLAPSED, consistent with genuinely neutral
// tournament sites replacing quasi-home neutral games in the modern era.
// Server component, static export, no client JS -- reads the staged exhibit
// via the shared loadArtifact() reader and renders every number verbatim,
// never recomputed, never re-rounded.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "Soccer Home-Advantage Decomposition",
  description:
    "Descriptive-only exhibit (edge_claimed: false): international soccer home advantage decomposed by venue (true-home vs neutral-site), era, and tournament type via the neutral-site natural control.",
  ...findingMeta("soccer-home-advantage"),
};

type VenueStats = { n: number; home_win_rate: number; draw_rate: number; away_win_rate: number; goal_diff: number };
type EraRow = {
  era: string;
  true_home_goal_diff: number;
  neutral_goal_diff: number;
  effect_goal_diff: number;
  n_true_home: number;
  n_neutral: number;
};
type TournamentRow = {
  bucket: string;
  n: number;
  true_home_n: number;
  true_home_goal_diff: number;
  neutral_n: number;
  neutral_goal_diff: number;
  effect_goal_diff: number;
};
type HomeAdvantageArtifact = Artifact & {
  headline?: string;
  method?: string;
  source_parquet?: string;
  observation_window?: { first_date: string; last_date: string; n_matches_played: number; note: string };
  venue?: { true_home: VenueStats; neutral: VenueStats };
  hfa_effect?: { goal_diff: number; home_win_rate: number };
  by_era?: EraRow[];
  by_tournament_type?: TournamentRow[];
  travel_leg?: { testable: boolean; note: string };
  confounds?: string[];
  receipt?: { committed_ledger: string; mechanisms: string[]; verdict: string };
};

const h1: CSSProperties = {
  fontFamily: "var(--font-display)",
  fontWeight: 500,
  fontSize: "clamp(2rem,4vw,2.75rem)",
  lineHeight: 1.08,
  letterSpacing: "-.015em",
  color: "var(--ink)",
  marginTop: 8,
};
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 16 };
const headline: CSSProperties = {
  marginTop: 20,
  padding: "16px 20px",
  background: "var(--paper-tint)",
  borderLeft: "3px solid var(--accent)",
  borderRadius: "var(--radius-card)",
  maxWidth: 760,
  fontSize: 16,
  fontWeight: 600,
  color: "var(--ink)",
  lineHeight: 1.55,
};
const noteBox: CSSProperties = {
  marginTop: 16,
  padding: "14px 18px",
  background: "var(--paper-tint)",
  borderLeft: "2px solid var(--rule-strong)",
  borderRadius: "var(--radius-card)",
  maxWidth: 700,
  fontSize: 14,
  color: "var(--ink-2)",
  lineHeight: 1.6,
};
const sectionH: CSSProperties = { ...lede, fontSize: 21, fontWeight: 600, color: "var(--ink)", marginTop: 40 };
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
  padding: "10px 14px",
  borderBottom: "1px solid var(--rule)",
  whiteSpace: "nowrap",
};

export default function SoccerHomeAdvantagePage() {
  const data = loadArtifact("soccer_home_advantage") as HomeAdvantageArtifact | null;

  if (!data || !data.venue) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Home advantage</p>
        <h1 style={h1}>Home advantage in international football, and why the gap grew</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { true_home, neutral } = data.venue;
  const win = data.observation_window;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Home advantage</p>
      <h1 style={h1}>Home advantage in international football, and why the gap grew</h1>
      <p style={lede}>
        {data.method} Window: {win?.first_date} to {win?.last_date}, n={win?.n_matches_played.toLocaleString()}{" "}
        matches played -- {win?.note}
      </p>

      <p style={headline}>{data.headline}</p>

      <section style={{ marginTop: 40 }}>
        <p style={sectionH}>Venue split</p>
        <div style={{ marginTop: 16, overflowX: "auto", maxWidth: 700 }}>
          <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 520 }}>
            <thead>
              <tr>
                <th style={th}>Venue</th>
                <th style={th}>n</th>
                <th style={th}>Home win</th>
                <th style={th}>Draw</th>
                <th style={th}>Away win</th>
                <th style={th}>Goal diff</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ ...td, fontWeight: 600 }}>True home</td>
                <td style={td} className="mono">{true_home.n.toLocaleString()}</td>
                <td style={td} className="mono">{true_home.home_win_rate}</td>
                <td style={td} className="mono">{true_home.draw_rate}</td>
                <td style={td} className="mono">{true_home.away_win_rate}</td>
                <td style={td} className="mono">{true_home.goal_diff}</td>
              </tr>
              <tr>
                <td style={{ ...td, fontWeight: 600 }}>Neutral</td>
                <td style={td} className="mono">{neutral.n.toLocaleString()}</td>
                <td style={td} className="mono">{neutral.home_win_rate}</td>
                <td style={td} className="mono">{neutral.draw_rate}</td>
                <td style={td} className="mono">{neutral.away_win_rate}</td>
                <td style={td} className="mono">{neutral.goal_diff}</td>
              </tr>
            </tbody>
          </table>
        </div>
        {data.hfa_effect ? (
          <p style={{ ...noteBox, marginTop: 16 }}>
            <strong style={{ color: "var(--ink)" }}>Effect &mdash; </strong>
            true-home minus neutral: goal-diff effect {data.hfa_effect.goal_diff}, home-win-rate effect{" "}
            {data.hfa_effect.home_win_rate}.
          </p>
        ) : null}
      </section>

      {data.by_era ? (
        <section style={{ marginTop: 40 }}>
          <p style={sectionH}>By era</p>
          <div style={{ marginTop: 16, overflowX: "auto", maxWidth: 700 }}>
            <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 520 }}>
              <thead>
                <tr>
                  <th style={th}>Era</th>
                  <th style={th}>True-home gd</th>
                  <th style={th}>Neutral gd</th>
                  <th style={th}>Effect</th>
                </tr>
              </thead>
              <tbody>
                {data.by_era.map((e) => (
                  <tr key={e.era}>
                    <td style={{ ...td, fontWeight: 600 }}>
                      {e.era} (n={e.n_true_home.toLocaleString()}/{e.n_neutral.toLocaleString()})
                    </td>
                    <td style={td} className="mono">{e.true_home_goal_diff}</td>
                    <td style={td} className="mono">{e.neutral_goal_diff}</td>
                    <td style={td} className="mono">{e.effect_goal_diff}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ ...noteBox, marginTop: 16 }}>
            The effect grew because the neutral-venue edge collapsed, not because true-home advantage rose -- true-
            home goal diff is flat across both eras (0.6743 to 0.6745), while the neutral-venue goal diff fell from
            0.4556 to 0.1760.
          </p>
        </section>
      ) : null}

      {data.by_tournament_type ? (
        <section style={{ marginTop: 40 }}>
          <p style={sectionH}>By tournament type</p>
          <div style={{ marginTop: 16, overflowX: "auto", maxWidth: 700 }}>
            <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 520 }}>
              <thead>
                <tr>
                  <th style={th}>Bucket</th>
                  <th style={th}>n</th>
                  <th style={th}>True-home gd</th>
                  <th style={th}>Neutral gd</th>
                  <th style={th}>Effect</th>
                </tr>
              </thead>
              <tbody>
                {data.by_tournament_type.map((b) => (
                  <tr key={b.bucket}>
                    <td style={{ ...td, fontWeight: 600 }}>{b.bucket}</td>
                    <td style={td} className="mono">{b.n.toLocaleString()}</td>
                    <td style={td} className="mono">{b.true_home_goal_diff}</td>
                    <td style={td} className="mono">{b.neutral_goal_diff}</td>
                    <td style={td} className="mono">{b.effect_goal_diff}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ ...noteBox, marginTop: 16 }}>
            The true-home edge is biggest in Qualifiers ({data.by_tournament_type.find((b) => b.bucket === "Qualifiers")?.effect_goal_diff}).
            Neutral games concentrate in Finals &amp; continental play (
            {data.by_tournament_type.find((b) => b.bucket === "Finals & continental")?.neutral_n.toLocaleString()} of{" "}
            {neutral.n.toLocaleString()} neutral matches).
          </p>
        </section>
      ) : null}

      {data.travel_leg ? (
        <p style={{ ...noteBox, marginTop: 24, maxWidth: 760 }}>
          <strong style={{ color: "var(--ink)" }}>Travel leg &mdash; </strong>
          {data.travel_leg.note}
        </p>
      ) : null}

      {data.confounds ? (
        <div style={{ marginTop: 24, maxWidth: 700 }}>
          <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 0, marginBottom: 8 }}>
            Confounds / notes
          </p>
          <ul style={{ ...lede, marginTop: 0, paddingLeft: 20, fontSize: 14, color: "var(--ink-2)" }}>
            {data.confounds.map((c) => (
              <li key={c}>{c}</li>
            ))}
            <li>Descriptive only -- no edge or ROI claim is made anywhere on this page.</li>
          </ul>
        </div>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <Receipt
          sourceArtifact="scripts/platformkit/analytics_showcase/out/soccer_home_advantage.json"
          asOf={data.generated_at || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>

      {data.receipt ? (
        <p style={{ ...lede, marginTop: 32 }}>
          This exhibit graduates the {data.receipt.mechanisms.length} mechanisms already{" "}
          {data.receipt.verdict.toLowerCase().replace(/_/g, " ")} in the committed mechanism ledger (
          {data.receipt.committed_ledger}) into a published page -- the numbers above are not recomputed here, only
          re-presented with their receipts.
        </p>
      ) : null}
    </div>
  );
}
