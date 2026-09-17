import type { Metadata } from "next";
import Link from "next/link";
import { Receipt } from "@/components/analytics/Receipt";
import { StateContrasts } from "@/components/analytics/state-contrasts/StateContrasts";
import { InspectorReadingTrail } from "@/components/analytics/InspectorReadingTrail";
import { loadStateContrasts } from "@/lib/analytics/stateContrasts.server";
import "./state-contrasts.css";

export const metadata: Metadata = {
  title: "State contrasts",
  description: "Published differences in outcome frequency between adjacent time-bucket populations.",
};

export default function StateContrastsPage() {
  const sports = loadStateContrasts();
  return <div className="sc-page">
    <p className="overline">Calibration / State contrasts</p>
    <h1>{sports.length ? "Compare adjacent state buckets." : "Compare published state buckets."}</h1>
    {!sports.length ? <>
      <InspectorReadingTrail id="state-contrasts" />
      <p className="sc-lede">The published state contrast snapshot is not available in this build.</p>
      <Link href="/analytics/browse/">Browse published modules</Link>
    </> : <>
    <p className="sc-lede">Select a sport and adjacent time buckets to inspect the published outcome-frequency difference while keeping both underlying populations in view.</p>
    <InspectorReadingTrail id="state-contrasts" />
    <StateContrasts sports={sports} />
    <div className="sc-receipt"><Receipt sourceArtifact="public/data/showcase/why_attribution.json" label="descriptive_only" verdict="descriptive_only" /></div>
    </>}
  </div>;
}
