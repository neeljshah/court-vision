import type { Metadata } from "next";
import { Receipt } from "@/components/analytics/Receipt";
import { StateContrasts } from "@/components/analytics/state-contrasts/StateContrasts";
import { loadStateContrasts } from "@/lib/analytics/stateContrasts.server";
import "./state-contrasts.css";

export const metadata: Metadata = {
  title: "State contrasts",
  description: "Published differences in outcome frequency between adjacent time-bucket populations.",
};

export default function StateContrastsPage() {
  const sports = loadStateContrasts();
  if (!sports.length) return <div className="sc-page"><p className="overline">Calibration / State contrasts</p><h1>Compare published state buckets.</h1><p className="sc-lede">The published state contrast snapshot is not available in this build.</p></div>;
  return <div className="sc-page">
    <p className="overline">Calibration / State contrasts</p>
    <h1>Compare adjacent state buckets.</h1>
    <p className="sc-lede">Select a sport and adjacent time buckets to inspect the published outcome-frequency difference while keeping both underlying populations in view.</p>
    <StateContrasts sports={sports} />
    <div className="sc-receipt"><Receipt sourceArtifact="public/data/showcase/why_attribution.json" label="descriptive_only" verdict="descriptive_only" /></div>
  </div>;
}
