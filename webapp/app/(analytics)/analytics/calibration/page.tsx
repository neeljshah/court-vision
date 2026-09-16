import type { Metadata } from "next";
import Link from "next/link";
import { CalibrationReliability } from "@/components/analytics/calibration/CalibrationReliability";
import { Receipt } from "@/components/analytics/Receipt";
import { loadCalibrationReliability } from "@/lib/analytics/calibrationReliability";
import { snapshot } from "@/lib/analytics/labHelpers";
import "./calibration.css";

export const metadata: Metadata = {
  title: "Calibration reliability",
  description: "Inspect published reliability bins, their observed-frequency intervals, and model-to-market calibration summaries.",
};

type MarketType = {
  description?: string;
  scored?: boolean;
  n_rows?: number;
  model_brier?: number | null;
  market_brier?: number | null;
  model_ece?: number | null;
  market_ece?: number | null;
};
type MarketArtifact = { market_types?: Record<string, MarketType> };

function sportFor(id: string): string {
  return id.startsWith("mlb_") ? "MLB" : id.startsWith("soccer_") ? "International soccer" : id;
}

function score(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toString() : "Not scored";
}

function lowerBrier(row: MarketType): string {
  if (!row.scored || row.model_brier == null || row.market_brier == null) return "No resolved outcome label";
  if (row.market_brier < row.model_brier) return "Market has lower Brier";
  if (row.market_brier > row.model_brier) return "Model has lower Brier";
  return "Equal published Brier";
}

export default function CalibrationPage() {
  const series = loadCalibrationReliability();
  const meta = series[0]?.meta;
  const marketData = snapshot<MarketArtifact>("calibration_by_market_type");
  const markets = Object.entries(marketData.market_types || {});
  const ci = meta?.ciPct || [null, null];

  return <div className="calibration-page">
    <p className="calibration-kicker">Measurement / Calibration</p>
    <h1 className="calibration-title">Inspect every reliability bin.</h1>
    <p className="calibration-intro">A reliability bin groups forecasts within a published probability range, then compares their mean forecast with the observed frequency. The diagonal is the calibrated reference; a point away from it shows the direction and size of that bin&apos;s published gap.</p>
    <p className="calibration-intro">For example, the published MLB model bin has a 5.12% mean forecast and a 23.31% observed frequency: 23.31% minus 5.12% is an 18.19 pp gap.</p>
    <p className="calibration-intro">Observed-frequency intervals use {meta?.nBoot?.toLocaleString("en-US") || "unpublished"} bootstrap resamples clustered by {meta?.clusterUnit || "the published cluster unit"}, with a {ci[0] ?? "unpublished"}% to {ci[1] ?? "unpublished"}% interval. Bins use a minimum floor of {meta?.minGamesPerBinFloor ?? "unpublished"} games; n counts ticks, not games.</p>
    <section className="calibration-definitions" aria-labelledby="calibration-definitions-title">
      <h2 id="calibration-definitions-title">Three different properties</h2>
      <dl>
        <div><dt>Brier score</dt><dd>The mean squared error of the forecast probability against the 0/1 outcome. Lower is better; it combines calibration and resolution.</dd></div>
        <div><dt>Calibration error</dt><dd>ECE and the reliability curve measure how far observed frequency sits from the forecast in each bin. This page shows the published reliability bins and ECE summaries.</dd></div>
        <div><dt>Sharpness</dt><dd>How far forecasts sit from the base rate. Sharpness is different from Brier and calibration error, and this page does not show a sharpness measure.</dd></div>
      </dl>
    </section>
    <section className="calibration-section">
      <h2>Reliability curves with uncertainty</h2>
      <p>Exact fields: calibration_stability.json -&gt; sports[sport].sides[side].bins[] -&gt; mean_p, mean_y, mean_y_ci, gap, gap_ci, n, n_games, and low_n.</p>
      <CalibrationReliability series={series} />
      <p>These reliability curves cover MLB and international soccer only. See <Link href="/analytics/research/calibration-by-game-checkpoint">calibration by game checkpoint</Link> for checkpoint evidence from other published corpora.</p>
    </section>
    <section className="calibration-section">
      <h2>Summary by market</h2>
      <p>Published Brier and expected calibration error scores, where resolved outcomes are available. Lower Brier means lower average squared probability error.</p>
      <div className="calibration-table-wrap" role="region" aria-label="Calibration summary by market" data-scroll-region>
        <table className="calibration-table"><thead><tr><th>Sport</th><th>Market</th><th>Model Brier</th><th>Market Brier</th><th>Model ECE</th><th>Market ECE</th><th>n</th><th>Published comparison</th></tr></thead><tbody>{markets.map(([id, row]) => <tr key={id}><td>{sportFor(id)}</td><td>{row.description || id}</td><td>{score(row.model_brier)}</td><td>{score(row.market_brier)}</td><td>{score(row.model_ece)}</td><td>{score(row.market_ece)}</td><td>{typeof row.n_rows === "number" ? row.n_rows.toLocaleString("en-US") : "Not published"}</td><td>{lowerBrier(row)}</td></tr>)}</tbody></table>
      </div>
      <p className="calibration-note">The scored MLB and international soccer rows publish lower market Brier values. The total row remains unscored because its source has no resolved outcome label.</p>
    </section>
    <div className="calibration-receipt"><Receipt sourceArtifact="public/data/showcase/calibration_stability.json" asOf={meta?.asOf || undefined} label="descriptive_only" verdict="descriptive_only" /></div>
  </div>;
}
