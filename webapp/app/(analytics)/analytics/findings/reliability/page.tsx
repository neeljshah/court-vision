import type { Metadata } from "next";
import { ReliabilityFinding } from "@/components/analytics/reliability-finding/ReliabilityFinding";
import { Receipt } from "@/components/analytics/Receipt";
import { findingMeta } from "@/lib/analytics/og";
import { loadReliabilityFinding } from "@/lib/analytics/reliabilityFinding.server";
import "@/components/analytics/reliability-finding/reliability-finding.css";
import { loadArtifact } from "@/lib/showcase.server";
import { FindingTemplate } from "@/components/analytics/findings/FindingTemplate";

export const metadata: Metadata = {
  title: "Reliability decomposition",
  description: "Published Murphy decomposition components and ten-bin reconstruction remainders, per sport and source.",
  ...findingMeta("reliability"),
};

export default function ReliabilityPage() {
  const sports = loadReliabilityFinding();
  const murphy = loadArtifact("murphy_decomposition");
  return <FindingTemplate slug="reliability" artifact={murphy}>
    <p className="rf-page-lede">This exhibit reports the direct Brier score alongside the published ten-bin reconstruction for each source. It does not assign the model-to-reference score difference to recalibration or any other single cause.</p>
    <ReliabilityFinding sports={sports} />
    <div className="rf-receipt"><Receipt sourceArtifact="public/data/showcase/murphy_decomposition.json" label="descriptive_only" verdict="descriptive_only" /></div>
  </FindingTemplate>;
}
