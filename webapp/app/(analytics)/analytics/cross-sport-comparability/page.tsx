import type { Metadata } from "next";
import { CrossSportComparability } from "@/components/analytics/cross-sport-comparability/CrossSportComparability";
import { loadCrossSportComparability } from "@/lib/analytics/crossSportComparability.server";
import "./cross-sport-comparability.css";

export const metadata: Metadata = {
  title: "Cross-sport comparability",
  description: "Published decisions about which cross-sport reliability measurements share a valid axis.",
};

export default function CrossSportComparabilityPage() {
  const data = loadCrossSportComparability();
  return <div className="csc-page"><p className="csc-kicker">Calibration / comparability gate</p><h1>Read the published comparability decisions first.</h1><p className="csc-intro">This view shows exactly which reliability-component comparisons are supported by the committed evidence, and which measurements remain outside that axis.</p><CrossSportComparability data={data} /></div>;
}
