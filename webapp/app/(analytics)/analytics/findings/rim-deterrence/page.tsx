// Rim-deterrence leaderboard -- a transparent on/off metric: does the share
// of opponent shots at the rim drop when this player is on the floor? The
// list is face-valid (Wembanyama, Gobert, Jaren Jackson Jr. top it, matching
// the eye test), but on/off bundles teammates and scheme into the delta --
// this is descriptive on-court association, not isolated individual
// causation. Server component, static export, no client JS, verbatim numbers.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "Who Bends The Shot Chart",
  description:
    "Descriptive-only exhibit (edge_claimed: false): a rim-deterrence leaderboard from real NBA on/off zone splits, floored at 500 on-court minutes -- and the roster confound made explicit.",
  ...findingMeta("rim-deterrence"),
};

type Leader = {
  rank: number;
  player_name: string;
  min_on: number;
  rim_share_allowed_on: number;
  rim_share_allowed_off: number;
  delta: number;
  rim_efg_delta?: number;
};
type SeasonBlock = { season: string; n_qualified: number; min_on_floor: number; leaders: Leader[] };
type RimDeterrenceArtifact = Artifact & {
  headline?: string;
  method?: string;
  metric_definition?: string;
  seasons?: SeasonBlock[];
  observation_window?: { seasons: string[]; note: string };
  confounds?: string[];
  receipt?: { source_parquets: string[] };
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

function SeasonTable({ block }: { block: SeasonBlock }) {
  return (
    <section style={{ marginTop: 40 }}>
      <p style={sectionH}>{block.season}</p>
      <p style={{ ...lede, fontSize: 14.5, marginTop: 6, color: "var(--ink-3)" }}>
        n qualified (min_on &ge; {block.min_on_floor.toLocaleString()}) = {block.n_qualified.toLocaleString()}
      </p>
      <div style={{ marginTop: 16, overflowX: "auto", maxWidth: 760 }}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}>
          <thead>
            <tr>
              <th style={th}>Rank</th>
              <th style={th}>Player</th>
              <th style={th}>Min</th>
              <th style={th}>Rim share on</th>
              <th style={th}>Rim share off</th>
              <th style={th}>Delta</th>
            </tr>
          </thead>
          <tbody>
            {block.leaders.map((r) => (
              <tr key={r.player_name}>
                <td style={td} className="mono">{r.rank}</td>
                <td style={{ ...td, fontWeight: 600 }}>{r.player_name}</td>
                <td style={td} className="mono">{r.min_on.toLocaleString()}</td>
                <td style={td} className="mono">{r.rim_share_allowed_on}</td>
                <td style={td} className="mono">{r.rim_share_allowed_off}</td>
                <td style={{ ...td, fontWeight: 600 }} className="mono">
                  {r.delta > 0 ? `+${r.delta}` : r.delta}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function RimDeterrencePage() {
  const data = loadArtifact("rim_deterrence") as RimDeterrenceArtifact | null;

  if (!data || !data.seasons || data.seasons.length === 0) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Rim deterrence</p>
        <h1 style={h1}>Who bends the shot chart: a rim-deterrence leaderboard</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const win = data.observation_window;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Rim deterrence</p>
      <h1 style={h1}>Who bends the shot chart: a rim-deterrence leaderboard</h1>
      <p style={lede}>{data.method}</p>
      {data.metric_definition ? <p style={{ ...lede, fontSize: 14.5, color: "var(--ink-3)" }}>{data.metric_definition}</p> : null}

      <p style={headline}>{data.headline}</p>

      {data.seasons.map((block) => (
        <SeasonTable key={block.season} block={block} />
      ))}

      <div style={{ marginTop: 32, maxWidth: 700 }}>
        <p style={sectionH}>The eye test agrees</p>
        <p style={lede}>
          Wembanyama, Gobert, Jaren Jackson Jr. -- the names at the top of this list are the names scouts already
          point to. That is the point of a transparent on/off number: it recovers what the eye test already knows,
          in public, from the shot-mix data itself.
        </p>
      </div>

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

      {win ? (
        <div style={{ marginTop: 24, maxWidth: 700 }}>
          <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 0, marginBottom: 8 }}>
            Observation window
          </p>
          <p style={{ ...lede, fontSize: 14, marginTop: 0 }}>
            {win.seasons.join(", ")} -- {win.note}.
          </p>
        </div>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <Receipt
          sourceArtifact="scripts/platformkit/analytics_showcase/out/rim_deterrence.json"
          asOf={data.generated_at || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>
    </div>
  );
}
