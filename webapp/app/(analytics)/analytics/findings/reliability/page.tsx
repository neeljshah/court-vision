import type { Metadata } from "next";
import { ReliabilityFinding } from "@/components/analytics/reliability-finding/ReliabilityFinding";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";
import { loadReliabilityFinding } from "@/lib/analytics/reliabilityFinding.server";
import "@/components/analytics/reliability-finding/reliability-finding.css";

export const metadata: Metadata = {
  title: "Reliability decomposition",
  description: "Published Murphy decomposition components and ten-bin reconstruction remainders, per sport and source.",
  ...findingMeta("reliability"),
};

export default function ReliabilityPage() {
  const sports = loadReliabilityFinding();
  return <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
    <p className="overline">Findings / Reliability</p>
    <h1 className="rf-page-title">The published reliability components need a closure check.</h1>
    <p className="rf-page-lede">This exhibit reports the direct Brier score alongside the published ten-bin reconstruction for each source. It does not assign the model-to-reference score difference to recalibration or any other single cause.</p>
    <ReliabilityFinding sports={sports} />
    <div className="rf-receipt"><Receipt sourceArtifact="public/data/showcase/murphy_decomposition.json" label="descriptive_only" verdict="descriptive_only" /></div>
  </div>;
}
