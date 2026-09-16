import type { Metadata } from "next";
import Link from "next/link";
import { ResidualAnatomy } from "@/components/analytics/residual-anatomy/ResidualAnatomy";
import { loadResidualAnatomy } from "@/lib/analytics/residualAnatomy.server";
import "./residual-anatomy.css";

export const metadata: Metadata = {
  title: "Residual anatomy",
  description: "Published residual volume and per-row residuals by time and probability bucket.",
};

export default function ResidualAnatomyPage() {
  const data = loadResidualAnatomy();
  return <div className="ra-page">
    <p className="ra-kicker">Calibration / Residual anatomy</p>
    <h1>Separate recorded volume from per-row residual.</h1>
    <p className="ra-intro">Each cell is a published time-bucket and probability-bucket segment from <code>sports[sport].segments[]</code>. Switch the cell measure, inspect its published fields, and compare the two rankings below each grid.</p>
    <section className="ra-explanation" aria-labelledby="ra-explanation-title">
      <h2 id="ra-explanation-title">Absolute residual is not reducible miscalibration</h2>
      <p>A forecast near 50% can have a large absolute residual on an individual resolved outcome while still being calibrated across comparable forecasts. Total absolute residual mass also grows with the number of rows. These fields describe recorded residual volume and per-row residual; they do not establish a correctable calibration gap or its cause.</p>
      <p>Use the <Link href="/analytics/calibration">calibration reliability view</Link> to compare forecasts with observed frequency across bins, and <Link href="/analytics/score-decomposition">score decomposition</Link> to inspect the published Brier components.</p>
    </section>
    <ResidualAnatomy data={data} />
  </div>;
}
