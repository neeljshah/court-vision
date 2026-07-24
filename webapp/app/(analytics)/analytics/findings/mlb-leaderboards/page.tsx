// MLB descriptive leaderboards -- a sibling honesty exhibit to
// effective-sample-size/retraction (DESIGN Sec. 1 + 4 + 11). Renders
// Statcast-derived catcher/umpire out-of-zone strike-rate and platoon-split
// leaderboards for a FIXED 2022-2023 corpus slice, beside their own honest
// nulls: an unstable park-factor read (0 of 29 rows finite) and a REJECTed
// umpire-totals gate. Server component, static export, no client JS -- reads
// the staged exhibit at build time via the shared loadArtifact() reader and
// renders every number verbatim, never recomputed, never re-rounded.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";

export const metadata: Metadata = {
  title: "MLB Leaderboards",
  description:
    "Descriptive-only exhibit (edge_claimed: false): MLB Statcast-derived catcher, umpire, and platoon leaderboards for a fixed 2022-2023 slice, shown beside two honest nulls -- an unstable park-factor read and a REJECTed umpire-totals gate.",
};

type NamedRate = { name: string; n_ooz_called: number; ooz_strike_rate: number };
type PlatoonRow = {
  name: string; rate_vs_l: number; rate_vs_r: number; platoon_delta: number; pa_vs_l: number; pa_vs_r: number;
};
type OozBoard = { label: string; floor?: string; n_qualified: number; top: NamedRate[]; bottom: NamedRate[] };

type Leaderboards = Artifact & {
  headline?: string;
  observation_window?: { seasons: string; corpus_id: string; as_of: string; note: string };
  catcher_ooz?: OozBoard;
  platoon_splits?: { label: string; floor?: string; n_qualified: number; top: PlatoonRow[] };
  umpire_ooz?: OozBoard;
  park_factor_null?: { headline: string; n_rows: number; n_finite_park_factor: number; n_nan: number; verdict: string };
  umpire_totals_gate?: {
    hypothesis: string; verdict: string; verdict_reason: string; n_umpires: number;
    fold_rmse_deltas: number[]; reading: string;
  };
  confounds?: string[];
};

const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 16 };
const windowChip: CSSProperties = { marginTop: 20, display: "inline-block", padding: "8px 14px", background: "var(--paper-tint)", border: "1px solid var(--rule-strong)", borderRadius: "var(--radius-chip)", fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 };
const sectionLabel: CSSProperties = { fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 40, marginBottom: 0 };
const caption: CSSProperties = { fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 8 };
const floorNote: CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--ink-3)", marginTop: 4 };
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", whiteSpace: "nowrap" };
const td: CSSProperties = { fontSize: 14.5, color: "var(--ink)", padding: "10px 14px", borderBottom: "1px solid var(--rule)", whiteSpace: "nowrap" };
const tableWrap: CSSProperties = { overflowX: "auto", maxWidth: 700 };
const boardsRow: CSSProperties = { display: "flex", flexWrap: "wrap", gap: 24, marginTop: 12 };
const boardCol: CSSProperties = { flex: "1 1 320px", minWidth: 280 };
const boardHead: CSSProperties = { fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginBottom: 6 };
const nullBox: CSSProperties = { marginTop: 12, padding: "16px 18px", background: "var(--paper-tint)", borderLeft: "2px solid var(--null)", borderRadius: "var(--radius-card)", maxWidth: 700 };
const rejectBox: CSSProperties = { marginTop: 12, padding: "16px 18px", background: "var(--paper-raised)", border: "1px solid var(--rule)", borderLeft: "2px solid var(--reject)", borderRadius: "var(--radius-card)", boxShadow: "var(--shadow-card)", maxWidth: 700 };
const rejectTag: CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--reject)", border: "1px solid var(--reject)", borderRadius: "var(--radius-chip)", padding: "2px 7px", textTransform: "uppercase" };
const rowLabel: CSSProperties = { fontWeight: 700, fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--ink-3)", marginTop: 12, marginBottom: 4 };
const rowBody: CSSProperties = { fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)", margin: 0 };
const confoundList: CSSProperties = { marginTop: 12, paddingLeft: 20, maxWidth: 700, fontSize: 14, lineHeight: 1.7, color: "var(--ink-3)" };

function OozTable({ rows, headLabel }: { rows: NamedRate[]; headLabel: string }) {
  return (
    <div>
      <p style={boardHead}>{headLabel}</p>
      <div style={tableWrap}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 280 }}>
          <thead><tr><th style={th}>Name</th><th style={th}>OOZ strike rate</th><th style={th}>n</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.name}-${i}`}>
                <td style={td}>{r.name}</td>
                <td style={{ ...td, fontWeight: 600 }} className="mono">{r.ooz_strike_rate.toFixed(3)}</td>
                <td style={td} className="mono">{r.n_ooz_called.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function MlbLeaderboardsPage() {
  const data = loadArtifact("mlb_descriptive_leaderboards") as Leaderboards | null;

  if (!data || !data.catcher_ooz) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / MLB leaderboards</p>
        <h1 style={h1}>Descriptive MLB leaderboards, with the nulls attached</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { headline, observation_window, catcher_ooz, platoon_splits, umpire_ooz, park_factor_null, umpire_totals_gate, confounds, generated_at } = data;
  const sourceArtifact = (data.source_artifact as string | undefined) || "scripts/platformkit/analytics_showcase/out/mlb_descriptive_leaderboards.json";

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / MLB leaderboards</p>
      <h1 style={h1}>Descriptive MLB leaderboards, with the nulls attached</h1>
      {headline ? <p style={lede}>{headline}</p> : null}

      {observation_window ? (
        <p style={windowChip}>
          Window: {observation_window.seasons.replace("_", "-")} Statcast slice ({observation_window.corpus_id}) &mdash; {observation_window.note}.
        </p>
      ) : null}

      {catcher_ooz ? (
        <>
          <p style={sectionLabel}>Catcher out-of-zone strike rate</p>
          <p style={caption}>{catcher_ooz.label}</p>
          {catcher_ooz.floor ? <p style={floorNote}>floor: {catcher_ooz.floor} &middot; n_qualified {catcher_ooz.n_qualified.toLocaleString()}</p> : null}
          <div style={boardsRow}>
            <div style={boardCol}><OozTable rows={catcher_ooz.top} headLabel="Top 15" /></div>
            <div style={boardCol}><OozTable rows={catcher_ooz.bottom} headLabel="Bottom 15" /></div>
          </div>
        </>
      ) : null}

      {platoon_splits ? (
        <>
          <p style={sectionLabel}>Platoon splits</p>
          <p style={caption}>{platoon_splits.label}</p>
          {platoon_splits.floor ? <p style={floorNote}>floor: {platoon_splits.floor} &middot; n_qualified {platoon_splits.n_qualified.toLocaleString()}</p> : null}
          <div style={{ ...tableWrap, marginTop: 12 }}>
            <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 600 }}>
              <thead><tr><th style={th}>Batter</th><th style={th}>vs LHP</th><th style={th}>vs RHP</th><th style={th}>Delta</th><th style={th}>PA (L/R)</th></tr></thead>
              <tbody>
                {platoon_splits.top.map((r, i) => (
                  <tr key={`${r.name}-${i}`}>
                    <td style={td}>{r.name}</td>
                    <td style={td} className="mono">{r.rate_vs_l.toFixed(3)}</td>
                    <td style={td} className="mono">{r.rate_vs_r.toFixed(3)}</td>
                    <td style={{ ...td, fontWeight: 600 }} className="mono">{r.platoon_delta.toFixed(3)}</td>
                    <td style={td} className="mono">{r.pa_vs_l.toLocaleString()} / {r.pa_vs_r.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {umpire_ooz ? (
        <>
          <p style={sectionLabel}>Umpire out-of-zone strike rate</p>
          <p style={caption}>{umpire_ooz.label}</p>
          <p style={floorNote}>n_qualified {umpire_ooz.n_qualified.toLocaleString()}</p>
          <div style={boardsRow}>
            <div style={boardCol}><OozTable rows={umpire_ooz.top} headLabel="Top 15" /></div>
            <div style={boardCol}><OozTable rows={umpire_ooz.bottom} headLabel="Bottom 15" /></div>
          </div>
        </>
      ) : null}

      {park_factor_null ? (
        <>
          <p style={sectionLabel}>Park factor &mdash; the null we didn't dress up</p>
          <p style={nullBox}>
            {park_factor_null.headline} {park_factor_null.n_finite_park_factor} of {park_factor_null.n_rows} rows had a finite park factor ({park_factor_null.n_nan} NaN).
            This is not published as a ranking &mdash; verdict: <strong style={{ color: "var(--ink)" }}>{park_factor_null.verdict}</strong>.
          </p>
        </>
      ) : null}

      {umpire_totals_gate ? (
        <>
          <p style={sectionLabel}>Umpire-totals gate &mdash; the sharp angle we tested and failed</p>
          <div style={rejectBox}>
            <span style={rejectTag}>{umpire_totals_gate.verdict}</span>
            <p style={rowLabel}>Hypothesis</p><p style={rowBody}>{umpire_totals_gate.hypothesis}</p>
            <p style={rowLabel}>Why it failed</p><p style={rowBody}>{umpire_totals_gate.verdict_reason}</p>
            <p style={rowLabel}>N umpires</p><p style={rowBody} className="mono">{umpire_totals_gate.n_umpires.toLocaleString()}</p>
            <p style={rowLabel}>Fold RMSE deltas (real vs. planted-null assignment)</p>
            <p style={rowBody} className="mono tnum">{umpire_totals_gate.fold_rmse_deltas.map((d) => d.toFixed(6)).join(", ")}</p>
            <p style={rowLabel}>Reading</p><p style={rowBody}>{umpire_totals_gate.reading}</p>
          </div>
        </>
      ) : null}

      {confounds?.length ? (
        <>
          <p style={sectionLabel}>Confounds</p>
          <ul style={confoundList}>{confounds.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </>
      ) : null}

      <div style={{ marginTop: 24 }}>
        <Receipt sourceArtifact={sourceArtifact} asOf={generated_at || undefined} label="descriptive_only" verdict="descriptive_only" />
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        Descriptive only, from a fixed 2022-2023 window &mdash; no predictive power, no edge, and no ROI is claimed anywhere on this page.
      </p>
    </div>
  );
}
