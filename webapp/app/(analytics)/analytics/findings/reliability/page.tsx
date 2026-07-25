// Reliability -- a flagship honesty exhibit, sibling to findings/effective-sample-size
// and findings/retraction (DESIGN Sec. 1 + 4 + 11). Shows the Murphy (1973) Brier
// decomposition per sport, model vs market: our model's Brier is WORSE than the
// market's, and the gap is driven by RESOLUTION (information we lack), not
// reliability (miscalibration) -- so recalibrating would not close it. Server
// component, static export, no client JS -- reads the staged exhibit via the
// shared loadArtifact() reader and renders every number verbatim, never
// recomputed, never re-rounded.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import { Receipt } from "@/components/analytics/Receipt";
import { ReliabilityDiagram } from "@/components/analytics/charts/ReliabilityDiagram";
import { findingMeta } from "@/lib/analytics/og";

export const metadata: Metadata = {
  title: "Reliability Diagrams",
  description:
    "Descriptive-only exhibit (edge_claimed: false): calibration reliability diagrams and the Murphy Brier decomposition, per sport, model vs market. The model trails the market on Brier; the gap is resolution (information), not reliability (calibration).",
  ...findingMeta("reliability"),
};

type Bin = { bin_lo: number; bin_hi: number; n: number; mean_p: number; mean_y: number };
type ProbStats = {
  n: number;
  brier: number;
  reliability: number;
  resolution: number;
  uncertainty: number;
  reconstructed_brier: number;
  bins: Bin[];
};
type SportEntry = { n_rows: number; model_prob: ProbStats; market_prob: ProbStats };
type MurphyArtifact = Artifact & {
  method?: string;
  sports?: Record<string, SportEntry>;
  verdict?: string;
};

const SPORT_LABEL: Record<string, string> = { mlb: "MLB", soccer_intl: "Soccer (Intl)" };
function sportLabel(sport: string): string {
  return SPORT_LABEL[sport] || sport.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Splits the single verdict string ("mlb: ... . soccer_intl: ... .") into its
// per-sport sentences -- the artifact publishes one string for all sports, this
// just re-anchors it per section without recomputing anything inside it.
function splitVerdict(v: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of v.split(/(?<=\))\.\s+(?=[a-z_]+:\s)/)) {
    const m = part.match(/^([a-z_]+):\s*(.*)$/s);
    if (m) out[m[1]] = m[2].trim().replace(/\.?$/, ".");
  }
  return out;
}

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

export default function ReliabilityPage() {
  const data = loadArtifact("murphy_decomposition") as MurphyArtifact | null;
  const sports = data?.sports ? Object.keys(data.sports) : [];

  if (!data || sports.length === 0) {
    return (
      <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
        <p className="overline">Findings / Reliability</p>
        <h1 style={h1}>Are our probabilities honest? The calibration diagrams</h1>
        <p style={lede}>Exhibit data not available in this build.</p>
      </div>
    );
  }

  const verdictParts = data.verdict ? splitVerdict(data.verdict) : {};

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Findings / Reliability</p>
      <h1 style={h1}>Are our probabilities honest? The calibration diagrams</h1>
      <p style={lede}>
        {data.method} Below, {sports.map(sportLabel).join(" and ")} model probabilities are checked against what
        actually happened, next to the market&apos;s own probabilities on the same games -- honestly: the model does
        not beat the market here.
      </p>

      <p style={headline}>
        The honest headline: our model&apos;s Brier score is WORSE than the market&apos;s on every sport measured
        here, and the gap is driven mainly by resolution (information the market has that we don&apos;t), not
        reliability (miscalibration). Recalibrating our probabilities would not close this gap -- we would need more
        or fresher information, not a better calibration curve.
      </p>

      {sports.map((sport) => {
        const s = data.sports![sport];
        return (
          <section key={sport} style={{ marginTop: 40 }}>
            <p style={sectionH}>{sportLabel(sport)}</p>
            <ReliabilityDiagram
              title={`${sportLabel(sport)}: predicted vs observed`}
              source="scripts/platformkit/analytics_showcase/out/murphy_decomposition.json"
              asOf={data.generated_at || data.as_of || ""}
              meta={`n=${s.n_rows.toLocaleString()}`}
              verdict="descriptive_only"
              series={[
                { label: "Model", bins: s.model_prob.bins, color: "var(--accent)" },
                { label: "Market", bins: s.market_prob.bins, color: "var(--ink-3)" },
              ]}
            />

            <div style={{ marginTop: 16, overflowX: "auto", maxWidth: 700 }}>
              <table className="tnum" style={{ borderCollapse: "collapse", width: "100%", minWidth: 520 }}>
                <thead>
                  <tr>
                    <th style={th}>Source</th>
                    <th style={th}>Brier</th>
                    <th style={th}>Reliability</th>
                    <th style={th}>Resolution</th>
                    <th style={th}>Uncertainty</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ ...td, fontWeight: 600 }}>Model</td>
                    <td style={td} className="mono">{s.model_prob.brier}</td>
                    <td style={td} className="mono">{s.model_prob.reliability}</td>
                    <td style={td} className="mono">{s.model_prob.resolution}</td>
                    <td style={td} className="mono">{s.model_prob.uncertainty}</td>
                  </tr>
                  <tr>
                    <td style={{ ...td, fontWeight: 600 }}>Market</td>
                    <td style={td} className="mono">{s.market_prob.brier}</td>
                    <td style={td} className="mono">{s.market_prob.reliability}</td>
                    <td style={td} className="mono">{s.market_prob.resolution}</td>
                    <td style={td} className="mono">{s.market_prob.uncertainty}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {verdictParts[sport] ? (
              <p style={{ ...noteBox, marginTop: 16 }}>
                <strong style={{ color: "var(--ink)" }}>Verdict &mdash; </strong>
                {verdictParts[sport]}
              </p>
            ) : null}
          </section>
        );
      })}

      <p style={{ ...noteBox, marginTop: 32, maxWidth: 760 }}>
        <strong style={{ color: "var(--ink)" }}>Caveat &mdash; </strong>
        These are within-game rows (MLB n={data.sports?.mlb ? data.sports.mlb.n_rows.toLocaleString() : "-"}), and
        rows from the same game are near-duplicates, not independent draws -- see{" "}
        <Link href="/analytics/findings/effective-sample-size" style={{ color: "var(--accent)", fontWeight: 600 }}>
          effective sample size
        </Link>{" "}
        for how far that deflates the honest, independent-game count. The bin means above are real, but treat their
        precision as bounded by that smaller effective sample, not by the raw row count.
      </p>

      <div style={{ marginTop: 24, maxWidth: 700 }}>
        <p style={{ ...lede, fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginTop: 0, marginBottom: 8 }}>
          Confounds / notes
        </p>
        <ul style={{ ...lede, marginTop: 0, paddingLeft: 20, fontSize: 14, color: "var(--ink-2)" }}>
          <li>Reliability &lt; resolution here means the miscalibration term is small relative to the information term -- the shortfall is not a curve-fitting problem.</li>
          <li>Uncertainty is the shared base-rate term (identical for model and market on the same games) -- it is not part of either side&apos;s gap.</li>
          <li>Within-game row dependence (see the caveat above) means bin means are less independent than their n suggests.</li>
          <li>Descriptive only -- no edge or ROI claim is made anywhere on this page.</li>
        </ul>
      </div>

      <div style={{ marginTop: 20 }}>
        <Receipt
          sourceArtifact="scripts/platformkit/analytics_showcase/out/murphy_decomposition.json"
          asOf={data.generated_at || data.as_of || undefined}
          label="descriptive_only"
          verdict="descriptive_only"
        />
      </div>

      <p style={{ ...lede, marginTop: 32 }}>
        We trail the close, not beat it -- the honest measurement here is that the market has information we don&apos;t
        yet see, and no amount of recalibrating our own probabilities substitutes for having it.
      </p>
    </div>
  );
}
