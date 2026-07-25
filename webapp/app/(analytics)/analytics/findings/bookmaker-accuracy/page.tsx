// We graded the bookmakers -- proportional-devig Brier on each book's own
// shared-game subset. Tennis match-winner: Pinnacle is barely sharpest.
// Soccer over/under 2.5: the books are a statistical dead heat. The honest
// headline is how CLOSE they all are, not who "wins". Server component,
// static export, no client JS -- reads the staged exhibit via the shared
// loadArtifact() reader and renders every number verbatim, never recomputed.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "We Graded the Bookmakers",
  description:
    "Descriptive-only exhibit (edge_claimed: false): a bookmaker-accuracy leaderboard, proportional-devig Brier score on shared-game subsets, for tennis match-winner and soccer over/under 2.5 goals.",
  ...findingMeta("bookmaker-accuracy"),
};

type BookRow = { book: string; brier: number; n: number };
type SportBlock = { market: string; outcome: string; n_shared: number; books: BookRow[] };
type ObsWindow = { source_parquet: string; n_rows_before_shared: number; note: string };
type BookmakerAccuracyArtifact = Artifact & {
  headline?: string;
  method?: string;
  sports?: { tennis: SportBlock; soccer: SportBlock };
  observation_window?: { tennis: ObsWindow; soccer: ObsWindow };
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

function LeaderboardTable({ sport, block, verdict }: { sport: string; block: SportBlock; verdict: string }) {
  return (
    <section style={{ marginTop: 40 }}>
      <p style={sectionH}>{sport}</p>
      <p style={{ ...lede, fontSize: 14.5, marginTop: 6, color: "var(--ink-3)" }}>
        Market: {block.market} &mdash; outcome: {block.outcome} &mdash; shared subset n={block.n_shared.toLocaleString()}
      </p>
      <div style={{ marginTop: 16, overflowX: "auto", maxWidth: 700 }}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 420 }}>
          <thead>
            <tr>
              <th style={th}>Book</th>
              <th style={th}>Brier</th>
              <th style={th}>n</th>
            </tr>
          </thead>
          <tbody>
            {block.books.map((b, i) => (
              <tr key={b.book}>
                <td style={{ ...td, fontWeight: 600 }}>
                  {b.book}
                  {i === 0 ? (
                    <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 700, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                      sharpest
                    </span>
                  ) : null}
                </td>
                <td style={td} className="mono">{b.brier}</td>
                <td style={td} className="mono">{b.n.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ ...noteBox, marginTop: 16 }}>{verdict}</p>
    </section>
  );
}

export default function BookmakerAccuracyPage() {
  const data = loadArtifact("bookmaker_accuracy") as BookmakerAccuracyArtifact | null;

  if (!data || !data.sports) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Grading the books</p>
        <h1 style={h1}>We graded the bookmakers</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { tennis, soccer } = data.sports;
  const win = data.observation_window;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Grading the books</p>
      <h1 style={h1}>We graded the bookmakers</h1>
      <p style={lede}>{data.method}</p>

      <p style={headline}>{data.headline}</p>

      <LeaderboardTable
        sport="Tennis -- match winner"
        block={tennis}
        verdict="Pinnacle is the (barely) sharpest book, as the literature predicts -- but the gap to Bet365 is 0.0005 Brier, tiny next to the market average sitting between them."
      />

      <LeaderboardTable
        sport="Soccer -- over/under 2.5 goals"
        block={soccer}
        verdict="A dead heat: Pinnacle and the market average tie at 0.2395, Bet365 a hair behind at 0.2396. On this market the books are statistically indistinguishable -- an honest null of separation."
      />

      <div style={{ marginTop: 32, maxWidth: 700 }}>
        <p style={sectionH}>How close they all are</p>
        <p style={lede}>
          Across both sports the spread between the sharpest and least-sharp book never exceeds 0.0005 Brier. No
          public book is meaningfully &quot;beatable&quot; by another on these markets -- the honest headline is the
          closeness itself, not a ranking. Being sharp is also not the same as being first: this exhibit measures
          accuracy at the timestamps captured, not who posts a line first.
        </p>
      </div>

      {win ? (
        <div style={{ marginTop: 24, maxWidth: 700 }}>
          <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 0, marginBottom: 8 }}>
            Observation window
          </p>
          <p style={{ ...lede, fontSize: 14, marginTop: 0 }}>
            Tennis: {win.tennis.source_parquet}, {win.tennis.n_rows_before_shared.toLocaleString()} rows before the
            shared-subset filter -- {win.tennis.note}.
          </p>
          <p style={{ ...lede, fontSize: 14, marginTop: 8 }}>
            Soccer: {win.soccer.source_parquet}, {win.soccer.n_rows_before_shared.toLocaleString()} rows before the
            shared-subset filter -- {win.soccer.note}.
          </p>
        </div>
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
          sourceArtifact="scripts/platformkit/analytics_showcase/out/bookmaker_accuracy.json"
          asOf={data.generated_at || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>
    </div>
  );
}
