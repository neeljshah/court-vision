// NBA Q4-vs-earlier per-36 shift -- a sibling honesty exhibit, published
// ALONGSIDE the clutch module it un-refuses (DESIGN Sec. 1 + 4 + 11). That
// module (/analytics/m/clutch_context) refused to call anything "clutch";
// this page is the honest, descriptive version of the same underlying split
// -- Q4-vs-Q1-3 per-36 rate shifts, with the blowout/garbage-time confound
// stated plainly rather than dressed up as a clutch signal. Server component,
// static export, no client JS -- reads the staged exhibit at build time via
// the shared loadArtifact() reader and renders every number verbatim, never
// recomputed, never re-rounded.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";

export const metadata: Metadata = {
  title: "The Q4 Shift",
  description:
    "Descriptive-only exhibit (edge_claimed: false): Q4-vs-Q1-3 per-36 rate shifts in points, rebounds, and assists for a fixed corpus, published beside the clutch module it un-refuses. Not a clutch metric, not predictive.",
};

type ShiftRow = {
  player_name: string;
  shift: number;
  q4_games: number;
  [key: string]: unknown;
};
type ShiftBoard = { top_risers: ShiftRow[]; top_fallers?: ShiftRow[] };

type Q4Shift = Artifact & {
  headline?: string;
  method?: string;
  un_refusal_note?: string;
  observation_window?: { n_games: number; seasons: string; note: string };
  floors?: string;
  n_considered?: number;
  n_qualified?: number;
  pts_shift?: ShiftBoard;
  reb_shift?: ShiftBoard;
  ast_shift?: ShiftBoard;
  confounds?: string[];
};

const CLUTCH_HREF = "/analytics/m/clutch_context";

const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const lede: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 700, marginTop: 16 };
const windowChip: CSSProperties = { marginTop: 20, display: "inline-block", padding: "8px 14px", background: "var(--paper-tint)", border: "1px solid var(--rule-strong)", borderRadius: "var(--radius-chip)", fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 };
const sectionLabel: CSSProperties = { fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 40, marginBottom: 0 };
const floorNote: CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--ink-3)", marginTop: 4 };
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 14px", borderBottom: "1px solid var(--rule-strong)", whiteSpace: "nowrap" };
const td: CSSProperties = { fontSize: 14.5, color: "var(--ink)", padding: "10px 14px", borderBottom: "1px solid var(--rule)", whiteSpace: "nowrap" };
const tableWrap: CSSProperties = { overflowX: "auto", maxWidth: 700 };
const boardsRow: CSSProperties = { display: "flex", flexWrap: "wrap", gap: 24, marginTop: 12 };
const boardCol: CSSProperties = { flex: "1 1 320px", minWidth: 280 };
const boardHead: CSSProperties = { fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginBottom: 6 };
const confoundList: CSSProperties = { marginTop: 12, paddingLeft: 20, maxWidth: 700, fontSize: 14, lineHeight: 1.7, color: "var(--ink-3)" };
// The un-refusal callout is THE point of the page (a refused clutch read,
// turned into an honest descriptive number) -- given a signal-colored left
// rail and raised card treatment so it reads as the lede's companion, not a
// footnote, unlike the quieter nullBox/rejectBox asides on sibling pages.
const unrefusalBox: CSSProperties = { marginTop: 24, padding: "20px 24px", background: "var(--paper-raised)", border: "1px solid var(--rule)", borderLeft: "3px solid var(--signal)", borderRadius: "var(--radius-card)", boxShadow: "var(--shadow-card)", maxWidth: 700 };
const unrefusalTag: CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--signal-ink)", border: "1px solid var(--signal-ink)", borderRadius: "var(--radius-chip)", padding: "2px 7px", textTransform: "uppercase" };
const unrefusalBody: CSSProperties = { fontSize: 15.5, lineHeight: 1.6, color: "var(--ink)", marginTop: 10 };
const methodLine: CSSProperties = { fontSize: 14, lineHeight: 1.6, color: "var(--ink-3)", maxWidth: 700, marginTop: 16 };

// Render verbatim: the artifact already carries 2-dp values (29.26, +13.52).
// toFixed(1) here would RE-ROUND a published number (29.26 -> "29.3"), which the
// no-invented-numbers rail forbids. String() prints exactly what the JSON holds.
const fmtShift = (v: number) => (v >= 0 ? `+${v}` : `${v}`);

// Splits the un_refusal_note on its first "refusal"/"refusals" and links just
// that word to the clutch module page -- the "we refused, here is the honest
// version" pointer the whole page hangs off of.
function NoteWithRefusalLink({ note }: { note: string }) {
  const m = /refusals?/i.exec(note);
  if (!m) return <>{note}</>;
  const start = m.index;
  const end = start + m[0].length;
  return (
    <>
      {note.slice(0, start)}
      <Link href={CLUTCH_HREF} style={{ fontWeight: 600 }}>
        {m[0]}
      </Link>
      {note.slice(end)}
    </>
  );
}

function ShiftTable({ rows, statKey, headLabel }: { rows: ShiftRow[]; statKey: "pts" | "reb" | "ast"; headLabel: string }) {
  const q4Key = `q4_${statKey}_per36`;
  const q13Key = `q13_${statKey}_per36`;
  return (
    <div>
      <p style={boardHead}>{headLabel}</p>
      <div style={tableWrap}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 480 }}>
          <thead>
            <tr>
              <th style={th}>Player</th>
              <th style={th}>Q4 /36</th>
              <th style={th}>Q1-3 /36</th>
              <th style={th}>Shift</th>
              <th style={th}>Q4 games</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.player_name}-${i}`}>
                <td style={td}>{r.player_name}</td>
                <td style={td} className="mono">{String(r[q4Key])}</td>
                <td style={td} className="mono">{String(r[q13Key])}</td>
                <td style={{ ...td, fontWeight: 600 }} className="mono">{fmtShift(r.shift)}</td>
                <td style={td} className="mono">{r.q4_games.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Q4ShiftPage() {
  const data = loadArtifact("nba_q4_shift") as Q4Shift | null;

  if (!data || !data.pts_shift) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Q4 shift</p>
        <h1 style={h1}>The fourth-quarter shift &mdash; what we could measure, and what we refused</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { headline, method, un_refusal_note, observation_window, floors, n_considered, n_qualified, pts_shift, reb_shift, ast_shift, confounds, generated_at } = data;
  const sourceArtifact = (data.source_artifact as string | undefined) || "scripts/platformkit/analytics_showcase/out/nba_q4_shift.json";

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Q4 shift</p>
      <h1 style={h1}>The fourth-quarter shift &mdash; what we could measure, and what we refused</h1>
      {headline ? <p style={lede}>{headline}</p> : null}

      {un_refusal_note ? (
        <div style={unrefusalBox}>
          <span style={unrefusalTag}>Un-refused</span>
          <p style={unrefusalBody}><NoteWithRefusalLink note={un_refusal_note} /></p>
        </div>
      ) : null}

      {method ? <p style={methodLine}><b style={{ color: "var(--ink-2)" }}>Method.</b> {method}</p> : null}

      {observation_window ? (
        <p style={windowChip}>
          Window: {observation_window.n_games.toLocaleString()} games ({observation_window.seasons}) &mdash; {observation_window.note}.
        </p>
      ) : null}

      {pts_shift ? (
        <>
          <p style={sectionLabel}>Points shift</p>
          {floors ? (
            <p style={floorNote}>
              floor: {floors} &middot; n_qualified {n_qualified?.toLocaleString()} of n_considered {n_considered?.toLocaleString()}
            </p>
          ) : null}
          <div style={boardsRow}>
            <div style={boardCol}><ShiftTable rows={pts_shift.top_risers} statKey="pts" headLabel="Top risers" /></div>
            {pts_shift.top_fallers ? (
              <div style={boardCol}><ShiftTable rows={pts_shift.top_fallers} statKey="pts" headLabel="Top fallers" /></div>
            ) : null}
          </div>
        </>
      ) : null}

      {reb_shift ? (
        <>
          <p style={sectionLabel}>Rebound shift</p>
          <div style={boardsRow}>
            <div style={boardCol}><ShiftTable rows={reb_shift.top_risers} statKey="reb" headLabel="Top risers" /></div>
          </div>
        </>
      ) : null}

      {ast_shift ? (
        <>
          <p style={sectionLabel}>Assist shift</p>
          <div style={boardsRow}>
            <div style={boardCol}><ShiftTable rows={ast_shift.top_risers} statKey="ast" headLabel="Top risers" /></div>
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
        Descriptive Q4-vs-Q1-3 per-36 splits only, from a fixed observation window &mdash; not
        a clutch metric, not predictive, and no edge or ROI is claimed anywhere on this page.
      </p>
    </div>
  );
}
