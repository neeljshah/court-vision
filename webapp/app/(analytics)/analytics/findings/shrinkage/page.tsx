// MLB shrinkage exhibit -- a sibling honesty exhibit to mlb-leaderboards (same
// data family: statcast_fuller_v1, 2022-2023 fixed window). Renders an
// empirical-Bayes / James-Stein shrinkage: small-sample rate "leaders" regress
// toward the group mean once a beta-binomial prior is fit per group. Server
// component, static export, no client JS -- reads the staged exhibit at build
// time via the shared loadArtifact() reader and renders every number verbatim,
// never recomputed, never re-rounded (rates are published to 4dp, alpha/beta/
// kappa to 2dp; this page uses String()/raw JSX interpolation only).
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";

export const metadata: Metadata = {
  title: "Shrinkage",
  description:
    "Descriptive-only exhibit (edge_claimed: false): empirical-Bayes shrinkage on MLB Statcast rate leaderboards for a fixed 2022-2023 slice -- small-sample leaders regress toward the group mean.",
};

type Row = { name: string; n: number; raw_rate: number; shrunk_rate: number };
type RegressorRow = Row & { regression: number };
type Group = {
  key: string;
  label: string;
  n_entities: number;
  pooled_mean: number;
  alpha: number;
  beta: number;
  kappa: number;
  floor?: string;
  biggest_regressors: RegressorRow[];
  top_by_shrunk: Row[];
};

type Shrinkage = Artifact & {
  headline?: string;
  method?: string;
  observation_window?: { seasons: string; corpus_id: string; as_of: string; note: string };
  groups?: Group[];
  confounds?: string[];
};

const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 16 };
const windowChip: CSSProperties = { marginTop: 20, display: "inline-block", padding: "8px 14px", background: "var(--paper-tint)", border: "1px solid var(--rule-strong)", borderRadius: "var(--radius-chip)", fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 };
const sectionLabel: CSSProperties = { fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 40, marginBottom: 0 };
const h2: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(1.3rem,2.4vw,1.6rem)", lineHeight: 1.2, color: "var(--ink)", marginTop: 8 };
const caption: CSSProperties = { fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 8 };
const floorNote: CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--ink-3)", marginTop: 4 };
const statRow: CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--ink-2)", marginTop: 8 };
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", whiteSpace: "nowrap" };
const td: CSSProperties = { fontSize: 14.5, color: "var(--ink)", padding: "10px 14px", borderBottom: "1px solid var(--rule)", whiteSpace: "nowrap" };
const tableWrap: CSSProperties = { overflowX: "auto", maxWidth: 700, marginTop: 12 };
const boardHead: CSSProperties = { fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 24, marginBottom: 0 };
const noteBox: CSSProperties = { marginTop: 20, padding: "16px 18px", background: "var(--paper-tint)", borderLeft: "2px solid var(--rule-strong)", borderRadius: "var(--radius-card)", maxWidth: 700 };
const noteBody: CSSProperties = { fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)", margin: 0 };
const confoundList: CSSProperties = { marginTop: 12, paddingLeft: 20, maxWidth: 700, fontSize: 14, lineHeight: 1.7, color: "var(--ink-3)" };

function signed(v: number): string {
  return v >= 0 ? `+${v}` : String(v);
}

function RegressorTable({ rows }: { rows: RegressorRow[] }) {
  return (
    <div style={tableWrap}>
      <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 560 }}>
        <thead>
          <tr>
            <th style={th}>Name</th>
            <th style={th}>n</th>
            <th style={th}>Raw rate</th>
            <th style={th}>Shrunk rate</th>
            <th style={th}>Moved by</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.name}-${i}`}>
              <td style={td}>{r.name}</td>
              <td style={td} className="mono">{r.n.toLocaleString()}</td>
              <td style={td} className="mono">{r.raw_rate}</td>
              <td style={{ ...td, fontWeight: 600 }} className="mono">{r.shrunk_rate}</td>
              <td style={td} className="mono">{signed(r.regression)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ShrunkTable({ rows }: { rows: Row[] }) {
  return (
    <div style={tableWrap}>
      <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 480 }}>
        <thead>
          <tr>
            <th style={th}>Name</th>
            <th style={th}>n</th>
            <th style={th}>Raw rate</th>
            <th style={th}>Shrunk rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.name}-${i}`}>
              <td style={td}>{r.name}</td>
              <td style={td} className="mono">{r.n.toLocaleString()}</td>
              <td style={td} className="mono">{r.raw_rate}</td>
              <td style={{ ...td, fontWeight: 600 }} className="mono">{r.shrunk_rate}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ShrinkagePage() {
  const data = loadArtifact("mlb_shrinkage") as Shrinkage | null;

  if (!data || !data.groups?.length) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Shrinkage</p>
        <h1 style={h1}>When the leaderboard regresses to the mean</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { headline, observation_window, groups, confounds, generated_at } = data;
  const sourceArtifact = (data.source_artifact as string | undefined) || "scripts/platformkit/analytics_showcase/out/mlb_shrinkage.json";

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Shrinkage</p>
      <h1 style={h1}>When the leaderboard regresses to the mean</h1>
      {headline ? <p style={lede}>{headline}</p> : null}

      <div style={noteBox}>
        <p style={noteBody}>
          How to read this: every rate below is pulled toward its group&apos;s pooled mean by an amount
          that depends on how few trials back it. Fit a beta-binomial prior per group (pooled mean m,
          concentration kappa = alpha + beta), then replace each raw rate with the posterior mean
          (k+alpha)/(n+alpha+beta). A player with tens of thousands of trials barely moves; a player with
          a few hundred can move a lot. This is a modeling choice &mdash; that the entities are exchangeable
          draws from one shared prior &mdash; not a newly discovered truth about any one name.
        </p>
      </div>

      {observation_window ? (
        <p style={windowChip}>
          Window: {observation_window.seasons.replace("_", "-")} Statcast slice ({observation_window.corpus_id}) &mdash; {observation_window.note}.
        </p>
      ) : null}

      {groups.map((g) => (
        <div key={g.key}>
          <p style={sectionLabel}>{g.key.replace(/_/g, " ")}</p>
          <h2 style={h2}>{g.label}</h2>
          <p style={statRow}>
            pooled_mean {g.pooled_mean} &middot; kappa {g.kappa} &middot; alpha {g.alpha} &middot; beta {g.beta} &middot; n_entities {g.n_entities.toLocaleString()}
          </p>
          {g.floor ? <p style={floorNote}>floor: {g.floor}</p> : null}

          <p style={boardHead}>Biggest regressors</p>
          <p style={caption}>The small-n rows the raw leaderboard overstated most.</p>
          <RegressorTable rows={g.biggest_regressors} />

          <p style={boardHead}>Leaderboard after shrinkage</p>
          <p style={caption}>Ranked by shrunk rate &mdash; the honest ranking.</p>
          <ShrunkTable rows={g.top_by_shrunk} />
        </div>
      ))}

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
        Descriptive statistical exhibit only. The shrunk rate is a regularized estimate under a modeling
        assumption, not a validated skill claim and not an edge or ROI claim anywhere on this page.
      </p>
    </div>
  );
}
