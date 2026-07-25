// League parity -- a small, honest 3-season descriptive exhibit: how concentrated
// are win totals across NBA teams each season (Gini/HHI on win shares), and how
// does that compare to raw win-pct spread and margin dispersion? Win-share Gini
// rose from 0.177 (2023-24) to 0.2004 (2025-26) -- the league looks more
// top-heavy over this window -- but two of the three seasons are flagged
// partial-vs-full-season, and games are pooled with any playoff rows (no
// game-type split), so this is 3 seasons of description, never a trend claim
// and never a forecast. Server component, static export, no client JS, verbatim
// numbers (never toFixed, never re-rounded).
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "A Parity Ledger",
  description:
    "Descriptive-only exhibit (edge_claimed: false): win-share Gini and HHI concentration per NBA season, 2023-24 through 2025-26, with partial-season and playoff-pooling caveats in plain sight.",
  ...findingMeta("league-parity"),
};

type SeasonRow = {
  season: string;
  n_games: number;
  n_teams: number;
  meets_games_floor: boolean;
  looks_partial_vs_full_season: boolean;
  win_share_gini: number;
  win_pct_stdev: number;
  margin_mean_abs: number;
  pct_close_games_le5: number;
};
type LeagueParityArtifact = Artifact & {
  methodology?: {
    unit?: string;
    game_filter?: string;
    win_share_gini?: string;
    win_share_hhi?: string;
    win_pct_stdev?: string;
    margin_dispersion?: string;
    not_a_forecast?: boolean;
    not_this?: string[];
  };
  declared_floors?: {
    min_games_per_season?: number;
    rule?: string;
    close_game_pts?: number;
    full_regular_season_games_reference?: number;
  };
  seasons?: SeasonRow[];
  extremes_descriptive?: {
    most_balanced_season?: { season: string; win_share_gini: number };
    least_balanced_season?: { season: string; win_share_gini: number };
  };
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
const partialTag: CSSProperties = {
  display: "inline-block",
  marginLeft: 8,
  fontSize: 10.5,
  fontWeight: 700,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  color: "var(--not-testable, #9a6b1a)",
  border: "1px solid currentColor",
  borderRadius: 4,
  padding: "1px 6px",
  verticalAlign: "middle",
};

export default function LeagueParityPage() {
  const data = loadArtifact("league_parity_index") as LeagueParityArtifact | null;

  if (!data || !data.seasons || data.seasons.length === 0) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / League parity</p>
        <h1 style={h1}>How competitive is each season? A parity ledger</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const meth = data.methodology || {};
  const floors = data.declared_floors || {};
  const ext = data.extremes_descriptive;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / League parity</p>
      <h1 style={h1}>How competitive is each season? A parity ledger</h1>
      <p style={lede}>
        {meth.unit ? meth.unit + ". " : ""}
        {meth.win_share_gini}
      </p>

      <p style={headline}>
        Win-share Gini rose from {ext?.most_balanced_season?.win_share_gini} in {ext?.most_balanced_season?.season}{" "}
        to {ext?.least_balanced_season?.win_share_gini} in {ext?.least_balanced_season?.season} -- across the three
        seasons on disk, the league looks more top-heavy, not more balanced. Two of those three seasons are partial
        vs. a full 1230-game season, so read this as a small, honest description, not a trend.
      </p>

      <div style={{ marginTop: 40, overflowX: "auto", maxWidth: 900 }}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 760 }}>
          <thead>
            <tr>
              <th style={th}>Season</th>
              <th style={th}>Games</th>
              <th style={th}>Teams</th>
              <th style={th}>Win-share Gini</th>
              <th style={th}>Win% stdev</th>
              <th style={th}>Mean abs margin</th>
              <th style={th}>% close (&le;5)</th>
            </tr>
          </thead>
          <tbody>
            {data.seasons.map((s) => (
              <tr key={s.season}>
                <td style={{ ...td, fontWeight: 600 }}>
                  {s.season}
                  {s.looks_partial_vs_full_season ? <span style={partialTag}>partial season</span> : null}
                  {!s.meets_games_floor ? (
                    <span style={{ ...partialTag, color: "var(--ink-3)" }}>below games floor</span>
                  ) : null}
                </td>
                <td style={td} className="mono">{s.n_games}</td>
                <td style={td} className="mono">{s.n_teams}</td>
                <td style={{ ...td, fontWeight: 600 }} className="mono">{s.win_share_gini}</td>
                <td style={td} className="mono">{s.win_pct_stdev}</td>
                <td style={td} className="mono">{s.margin_mean_abs}</td>
                <td style={td} className="mono">{s.pct_close_games_le5}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 32, maxWidth: 700 }}>
        <p style={sectionH}>Methodology and confounds</p>
        <ul style={{ ...lede, marginTop: 12, paddingLeft: 20, fontSize: 14, color: "var(--ink-2)" }}>
          {meth.game_filter ? <li>{meth.game_filter}</li> : null}
          {meth.win_share_hhi ? <li>{meth.win_share_hhi}</li> : null}
          {meth.win_pct_stdev ? <li>{meth.win_pct_stdev}</li> : null}
          {meth.margin_dispersion ? <li>{meth.margin_dispersion}</li> : null}
          {floors.rule ? (
            <li>
              Games floor: {floors.min_games_per_season} per season -- {floors.rule}. Full-season reference ={" "}
              {floors.full_regular_season_games_reference} games.
            </li>
          ) : null}
          {(meth.not_this || []).map((n) => (
            <li key={n}>{n}</li>
          ))}
          <li>Descriptive only -- no edge or ROI claim is made anywhere on this page.</li>
        </ul>
      </div>

      <div style={{ marginTop: 20 }}>
        <Receipt
          sourceArtifact="scripts/platformkit/analytics_showcase/out/league_parity_index.json"
          asOf={data.generated_at || data.as_of || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>
    </div>
  );
}
