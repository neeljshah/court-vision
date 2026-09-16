import type { Metadata } from "next";
import { ScoreDecomposition } from "@/components/analytics/score-decomposition/ScoreDecomposition";
import { loadScoreDecomposition } from "@/lib/analytics/scoreDecomposition";
import "./score-decomposition.css";

export const metadata: Metadata = {
  title: "Score decomposition",
  description: "Published Brier score components and reconstruction remainders.",
};

export default function ScoreDecompositionPage() {
  const sports = loadScoreDecomposition();
  return <div className="sd-page"><p className="sd-kicker">Calibration / Brier audit</p><h1>Inspect the Brier reconstruction remainder.</h1><p className="sd-intro">This view separates the published reliability, resolution, and uncertainty components for each population, then shows the difference between each binned reconstruction and the published Brier score.</p><ScoreDecomposition sports={sports} /></div>;
}
