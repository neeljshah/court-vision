import type { Metadata } from "next";
import Link from "next/link";
import { Receipt } from "@/components/analytics/Receipt";
import { StateReliability } from "@/components/analytics/state-reliability/StateReliability";
import { loadStateReliability } from "@/lib/analytics/stateReliability.server";
import "./state-reliability.css";

export const metadata: Metadata = {
  title: "State reliability",
  description: "Inspect published state-conditioned calibration rows and source-specific support by sport.",
};

export default function StateReliabilityPage() {
  const sports = loadStateReliability();
  return <div className="sr-page">
    <p className="sr-kicker">Measurement / State-conditioned reliability</p>
    <h1>Inspect reliability across the published game-state grid.</h1>
    <p className="sr-lede">State-conditioned reliability is a different object from aggregate reliability: it groups published forecasts by both game phase and probability band. Use the grids to compare the recorded model and reference rows without assuming their matching labels identify the same predictions.</p>
    <p className="sr-lede">For aggregate reliability bins and bootstrap intervals, see <Link href="/analytics/calibration">Calibration reliability</Link>. Those bins summarize a different published grouping.</p>
    <StateReliability sports={sports} />
    <div className="sr-receipt"><Receipt sourceArtifact="public/data/showcase/state_conditioned_calibration.json" label="descriptive_only" verdict="descriptive_only" /></div>
  </div>;
}
