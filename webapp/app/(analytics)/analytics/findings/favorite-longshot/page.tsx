// Is the betting market calibrated? A favorite-longshot bias audit, pregame,
// cross-sport. This grades THE MARKET's own calibration -- not our model. We
// do not claim to beat the market anywhere on this page. Tennis shows a
// mild, monotone favorite-longshot bias; MLB moneyline is essentially
// efficient. Server component, static export, no client JS -- reads the
// staged exhibit via the shared loadArtifact() reader and renders every
// number verbatim, never recomputed, never re-rounded.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "Is the Market Calibrated?",
  description:
    "Descriptive-only exhibit (edge_claimed: false): a favorite-longshot bias audit of the betting market's own calibration, pregame, cross-sport -- tennis match winner and MLB moneyline, bucketed with Wilson intervals.",
  ...findingMeta("favorite-longshot"),
};

type Bucket = { lo: number; hi: number; n: number; impl: number; real: number; gap: number; wilson_lo: number; wilson_hi: number };
type SportBlock = { book: string; market: string; n_total: number; buckets: Bucket[]; verdict: string };
type FlbArtifact = Artifact & {
  headline?: string;
  method?: string;
  grades?: string;
  sports?: { tennis: SportBlock; mlb: SportBlock };
  observation_window?: { note: string };
  confounds?: string[];
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

function BucketTable({ sport, block }: { sport: string; block: SportBlock }) {
  return (
    <section style={{ marginTop: 40 }}>
      <p style={sectionH}>{sport}</p>
      <p style={{ ...lede, fontSize: 14.5, marginTop: 6, color: "var(--ink-3)" }}>
        {block.book} &mdash; {block.market} &mdash; n={block.n_total.toLocaleString()}
      </p>
      <div style={{ marginTop: 16, overflowX: "auto", maxWidth: 760 }}>
        <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}>
          <thead>
            <tr>
              <th style={th}>Implied bucket</th>
              <th style={th}>n</th>
              <th style={th}>Mean implied</th>
              <th style={th}>Realized fav win</th>
              <th style={th}>Gap</th>
              <th style={th}>95% Wilson</th>
            </tr>
          </thead>
          <tbody>
            {block.buckets.map((b) => (
              <tr key={`${b.lo}-${b.hi}`}>
                <td style={td} className="mono">[{b.lo}, {b.hi})</td>
                <td style={td} className="mono">{b.n.toLocaleString()}</td>
                <td style={td} className="mono">{b.impl}</td>
                <td style={td} className="mono">{b.real}</td>
                <td style={td} className="mono">{b.gap > 0 ? `+${b.gap}` : b.gap}</td>
                <td style={td} className="mono">({b.wilson_lo}, {b.wilson_hi})</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ ...noteBox, marginTop: 16 }}>
        <strong style={{ color: "var(--ink)" }}>Verdict &mdash; </strong>
        {block.verdict}.
      </p>
    </section>
  );
}

export default function FavoriteLongshotPage() {
  const data = loadArtifact("market_favorite_longshot") as FlbArtifact | null;

  if (!data || !data.sports) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Market calibration</p>
        <h1 style={h1}>Is the betting market calibrated? A favorite-longshot audit</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const { tennis, mlb } = data.sports;

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Market calibration</p>
      <h1 style={h1}>Is the betting market calibrated? A favorite-longshot audit</h1>
      <p style={lede}>
        {data.method} This exhibit grades {data.grades || "the market, not our model"} -- we do not claim to beat the
        market anywhere here. The result reinforces that the market is efficient and well-calibrated.
      </p>

      <p style={headline}>{data.headline}</p>

      <BucketTable sport="Tennis -- match winner" block={tennis} />
      <BucketTable sport="MLB -- moneyline" block={mlb} />

      {data.observation_window ? (
        <div style={{ marginTop: 24, maxWidth: 700 }}>
          <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 0, marginBottom: 8 }}>
            Observation window
          </p>
          <p style={{ ...lede, fontSize: 14, marginTop: 0 }}>{data.observation_window.note}.</p>
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
          </ul>
        </div>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <Receipt
          sourceArtifact="scripts/platformkit/analytics_showcase/out/market_favorite_longshot.json"
          asOf={data.generated_at || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        This is also a calibration exhibit, alongside{" "}
        <Link href="/analytics/findings/reliability" style={{ color: "var(--accent)", fontWeight: 600 }}>
          reliability
        </Link>{" "}
        (which checks our own probabilities, not the market&apos;s) and{" "}
        <Link href="/analytics/findings/league-parity" style={{ color: "var(--accent)", fontWeight: 600 }}>
          league parity
        </Link>{" "}
        (a different descriptive read on competitive balance).
      </p>
    </div>
  );
}
