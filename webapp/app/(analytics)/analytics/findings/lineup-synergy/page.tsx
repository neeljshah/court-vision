// Lineup-synergy ledger -- a descriptive five-man metric: does the lineup's
// observed net rating beat what its members' individual on/off numbers would
// predict? The Grizzlies' Jackson-Morant-Bane-Edey-Wells five topped 2024-25
// at +24.32 net-per-48 above expected, but this is a single season, a small-
// minutes floor, and the "expected" baseline is itself roster-confounded.
// Server component, static export, no client JS, verbatim numbers.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "Greater Than The Sum Of Their Parts",
  description:
    "Descriptive-only exhibit (edge_claimed: false): a five-man lineup-synergy ledger from real NBA on/off stint data -- which units beat what their individual parts predict, with the single-season and small-minutes confounds made explicit.",
  ...findingMeta("lineup-synergy"),
};

type LineupRow = {
  rank: number;
  members: string[];
  team_id: number;
  n_games: number;
  min: number;
  net_per48: number;
  expected_net_per48: number;
  synergy_residual: number;
};
type LineupSynergyArtifact = Artifact & {
  headline?: string;
  method?: string;
  metric_definition?: string;
  season?: string;
  n_qualified?: number;
  min_floor_note?: string;
  top?: LineupRow[];
  bottom?: LineupRow[];
  observation_window?: { season: string; note: string };
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

function LineupTable({ title, rows, note }: { title: string; rows: LineupRow[]; note?: string }) {
  return (
    <section style={{ marginTop: 40 }}>
      <p style={sectionH}>{title}</p>
      {note ? <p style={{ ...lede, fontSize: 14.5, marginTop: 6, color: "var(--ink-3)" }}>{note}</p> : null}
      <div style={{ marginTop: 16, overflowX: "auto", maxWidth: 900 }}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 760 }}>
          <thead>
            <tr>
              <th style={th}>Rank</th>
              <th style={th}>Five-man lineup</th>
              <th style={th}>Min</th>
              <th style={th}>Net per 48</th>
              <th style={th}>Expected</th>
              <th style={th}>Synergy</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${title}-${r.rank}`}>
                <td style={td} className="mono">{r.rank}</td>
                <td style={{ ...td, fontWeight: 600, whiteSpace: "normal" }}>{r.members.join(", ")}</td>
                <td style={td} className="mono">{r.min.toLocaleString()}</td>
                <td style={td} className="mono">{r.net_per48 > 0 ? `+${r.net_per48}` : r.net_per48}</td>
                <td style={td} className="mono">{r.expected_net_per48 > 0 ? `+${r.expected_net_per48}` : r.expected_net_per48}</td>
                <td style={{ ...td, fontWeight: 600 }} className="mono">
                  {r.synergy_residual > 0 ? `+${r.synergy_residual}` : r.synergy_residual}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function LineupSynergyPage() {
  const data = loadArtifact("lineup_synergy") as LineupSynergyArtifact | null;

  if (!data || !data.top || data.top.length === 0) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Lineup synergy</p>
        <h1 style={h1}>Greater than the sum of their parts: a lineup-synergy ledger</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const win = data.observation_window;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Lineup synergy</p>
      <h1 style={h1}>Greater than the sum of their parts: a lineup-synergy ledger</h1>
      <p style={lede}>{data.method}</p>
      {data.metric_definition ? <p style={{ ...lede, fontSize: 14.5, color: "var(--ink-3)" }}>{data.metric_definition}</p> : null}

      <p style={headline}>{data.headline}</p>

      <p style={{ ...lede, fontSize: 14.5, marginTop: 24, color: "var(--ink-3)" }}>
        {data.season} -- n qualified (all 5 members individually qualified) = {data.n_qualified?.toLocaleString()}
      </p>

      <LineupTable title="Top synergy: outperformed their parts" rows={data.top} note={data.min_floor_note} />
      {data.bottom ? <LineupTable title="Bottom synergy: underperformed their parts" rows={data.bottom} /> : null}

      {data.confounds ? (
        <div style={{ marginTop: 32, maxWidth: 700 }}>
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
            {win.season} -- {win.note}.
          </p>
        </div>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <Receipt
          sourceArtifact="scripts/platformkit/analytics_showcase/out/lineup_synergy.json"
          asOf={data.generated_at || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>
    </div>
  );
}
