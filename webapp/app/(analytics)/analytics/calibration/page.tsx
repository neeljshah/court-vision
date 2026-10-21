// /analytics/calibration/ -- the T2 calibration page (DESIGN_PRINCIPLES section 3): header with
// status line; verdict table (CANONICAL_FIGURES); reliability diagrams with game-cluster
// intervals; Brier decomposition; sharpness; coverage; inspector links; summary by market;
// common footer (Limitations, Reproduce, Source path, Change log). Build-time only.
import type { Metadata } from "next";
import Link from "next/link";
import { CalibrationReliability } from "@/components/analytics/calibration/CalibrationReliability";
import { Term, VerdictLabel } from "@/components/evidence";
import { CalibrationVerdictTable, verdictRows } from "@/components/analytics/calibration/CalibrationVerdictTable";
import { CalibrationDecomposition, CalibrationSharpness } from "@/components/analytics/calibration/CalibrationDecomposition";
import { InspectorReadingTrail } from "@/components/analytics/InspectorReadingTrail";
import { Receipt } from "@/components/analytics/Receipt";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { QuotedOnList } from "@/components/analytics/QuotedOnList";
import { loadCalibrationReliability } from "@/lib/analytics/calibrationReliability";
import { snapshot } from "@/lib/analytics/labHelpers";
import { canonicalFigures, CANONICAL_PATH } from "@/lib/canonicalFigures.server";
import "./calibration.css";

export const metadata: Metadata = {
  title: "Calibration",
  description: "Calibration against the market by sport, market and checkpoint: verdicts, reliability bins with game-cluster intervals, Brier decomposition and sharpness.",
};

type MarketType = {
  description?: string; scored?: boolean; n_rows?: number;
  model_brier?: number | null; market_brier?: number | null; model_ece?: number | null; market_ece?: number | null;
};
type MarketArtifact = { market_types?: Record<string, MarketType> };

const sportFor = (id: string) => (id.startsWith("mlb_") ? "MLB" : id.startsWith("soccer_") ? "International soccer" : id);
const score = (v: number | null | undefined) => (typeof v === "number" && Number.isFinite(v) ? v.toFixed(4) : "Not scored");

export default function CalibrationPage() {
  const series = loadCalibrationReliability();
  const meta = series[0]?.meta;
  const markets = Object.entries(snapshot<MarketArtifact>("calibration_by_market_type").market_types || {});
  const ci = meta?.ciPct || [null, null];
  const rows = verdictRows(canonicalFigures());
  const pregame = rows.filter((f) => f.n_unit !== "games");
  const trails = pregame.filter((f) => f.verdict === "TRAILS_CLOSE").length;
  const behind = rows.filter((f) => f.verdict === "BEHIND").length;
  const asOf = rows.map((f) => f.as_of).sort().pop() ?? null;
  const sports = Array.from(new Set(series.map((s) => s.sport)));

  return <div className="calibration-page">
    <h1 className="calibration-title">Calibration against the market</h1>
    <p className="calibration-intro">Verdict: pregame, the model trails the <Term id="devigged-close">devigged close</Term> on MLB moneyline and soccer over/under 2.5, and matches it on NBA moneyline only because that sample is too small to tell. In play, its win probabilities score behind the live Kalshi price on the same ticks. Every row below is scored by <Term id="brier">Brier score</Term> (lower is better) and shows its n, 95% interval, as-of date and receipt.</p>
    <p className="cal-status" data-testid="status-line">
      Status: <VerdictLabel verdict="TRAILS_CLOSE" qualifier={false} /> on {trails} of {pregame.length} pregame rows,{" "}
      <VerdictLabel verdict="BEHIND" qualifier={false} /> on {behind} of {rows.length - pregame.length} in-play rows &middot; as of {asOf ?? "not staged"}
      <ReceiptChip sourceArtifact={CANONICAL_PATH} asOf={asOf} verified="edge_claimed:false" verdict="TRAILS_CLOSE" />
    </p>

    <section className="calibration-section" aria-labelledby="verdicts-h">
      <h2 id="verdicts-h">Verdict table</h2>
      <p><Term id="brier">Brier</Term> is the mean squared error of the probability; lower is better. The 0.2500 baseline is a constant 50% forecast. MATCHES_CLOSE carries UNDERPOWERED where the row&apos;s interval is wider than its <Term id="mde">minimum detectable effect</Term>: not resolved, not parity.</p>
      <CalibrationVerdictTable figures={canonicalFigures()} />
    </section>

    <section className="calibration-section" aria-labelledby="reliability-h">
      <h2 id="reliability-h">Reliability diagrams with game-cluster intervals</h2>
      <p>Each point is one probability bin: mean forecast against observed frequency, with the diagonal as the calibrated reference. Intervals use {meta?.nBoot?.toLocaleString("en-US") || "unpublished"} bootstrap resamples clustered by {meta?.clusterUnit || "the published cluster unit"} ({ci[0] ?? "?"}% to {ci[1] ?? "?"}%). Bins under the {meta?.minGamesPerBinFloor ?? "published"}-game floor are hollow and marked below floor. n counts ticks; the table gives games per bin.</p>
      <InspectorReadingTrail id="calibration" />
      <CalibrationReliability series={series} />
    </section>

    <section className="calibration-section" aria-labelledby="decomp-h">
      <h2 id="decomp-h">Brier decomposition</h2>
      <p><Term id="calibration-vs-resolution">Murphy decomposition</Term>: Brier = reliability - resolution + uncertainty, computed from the published bins. Within-bin spread is not published, so the binned total sits near, not on, the published Brier.</p>
      <CalibrationDecomposition series={series} />
    </section>

    <section className="calibration-section" aria-labelledby="sharp-h">
      <h2 id="sharp-h">Sharpness</h2>
      <p>How forecasts spread across the probability bins. A sharper forecaster puts more forecasts near 0% and 100%; sharpness is only useful when the bins above stay calibrated.</p>
      {sports.map((s) => <CalibrationSharpness key={s} series={series} sport={s} />)}
    </section>

    <section className="calibration-section" aria-labelledby="coverage-h">
      <h2 id="coverage-h">Coverage</h2>
      <p data-testid="coverage">Coverage of interval forecasts: <VerdictLabel verdict="NOT_TESTABLE" qualifier={false} /> in this snapshot. The rows above are binary probabilities; no nominal-level interval forecasts are published here, so no empirical coverage is printed.</p>
    </section>

    <section className="calibration-section" aria-labelledby="inspect-h">
      <h2 id="inspect-h">Inspectors</h2>
      <ul>
        <li><Link href="/analytics/state-reliability/">State-conditioned reliability</Link>: the same bins split by game phase.</li>
        <li><Link href="/analytics/research/calibration-by-game-checkpoint/">Calibration by game checkpoint</Link>: checkpoint evidence from other corpora.</li>
        <li><Link href="/analytics/forecaster/">Forecaster</Link> and <Link href="/analytics/compare/">compare</Link>: one forecast against the market reference.</li>
        <li>Each row of the reliability table has an Inspect bin control that opens that bin&apos;s worked example.</li>
      </ul>
    </section>

    <section className="calibration-section" aria-labelledby="market-h">
      <h2 id="market-h">Summary by market</h2>
      <p>Published Brier (lower is better) and expected calibration error, where resolved outcomes exist.</p>
      <div className="calibration-table-wrap" role="region" aria-label="Calibration summary by market" data-scroll-region tabIndex={0}>
        <table className="calibration-table"><thead><tr><th>Sport</th><th>Market</th><th>Model Brier (lower is better)</th><th>Market Brier</th><th>Baseline Brier</th><th>Model ECE</th><th>Market ECE</th><th>n rows</th></tr></thead>
          <tbody>{markets.map(([id, row]) => <tr key={id}><td>{sportFor(id)}</td><td>{row.description || id}</td><td>{score(row.model_brier)}</td><td>{score(row.market_brier)}</td><td>0.2500</td><td>{score(row.model_ece)}</td><td>{score(row.market_ece)}</td><td>{typeof row.n_rows === "number" ? row.n_rows.toLocaleString("en-US") : "Not published"}</td></tr>)}</tbody></table>
      </div>
    </section>

    <section className="cal-limits" aria-labelledby="limits-h">
      <h2 id="limits-h">Limitations</h2>
      <ul>
        <li>Sample and independence: reliability n counts ticks; ticks within a game are not independent, which is why intervals are clustered by game.</li>
        <li>Scope: reliability bins cover MLB and international soccer only; the pregame verdicts come from one recompute memo dated 2026-09-24.</li>
        <li>What this does not establish: a calibrated forecast that trails or matches the market is not a reason to trade against it.</li>
      </ul>
      <h3>Reproduce</h3>
      <p><code>python scripts/platformkit/analytics_showcase/check_all.py</code></p>
      <h3>Source path</h3>
      <p><code>{CANONICAL_PATH}</code>; <code>webapp/public/data/showcase/calibration_stability.json</code>; <code>docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md</code></p>
      <h3>Quoted on</h3>
      <QuotedOnList artifact="docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md" />
      <QuotedOnList artifact="calibration_stability.json" />
      <h3>Change log</h3>
      <p>2026-10-20: rebuilt to the T2 template (verdict table, decomposition, sharpness, coverage; validated palette).</p>
    </section>
    <div className="calibration-receipt"><Receipt sourceArtifact="public/data/showcase/calibration_stability.json" asOf={meta?.asOf || undefined} label="descriptive_only" verdict="descriptive_only" /></div>
  </div>;
}
