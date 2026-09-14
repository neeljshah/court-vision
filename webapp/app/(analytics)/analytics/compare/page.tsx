import type { Metadata } from "next";
import "../workspace.css";
import "./compare.css";
import { CompareExperience } from "@/components/analytics/compare/CompareExperience";

export const metadata: Metadata = {
  title: "Compare profiles",
  description: "Compare two descriptive Atlas profiles in the same published pack. Raw values and within-pack percentiles only; no projection or quality ranking.",
};
export const dynamic = "force-static";

export default function CompareProfilesPage() {
  return <div className="cv-workspace"><div className="cv-workspace-inner compare-page">
    <header className="compare-header"><p className="cv-eyebrow"><span className="cv-square" />Published Atlas</p><h1>Compare profiles</h1><p>Place two profiles from one pack side by side. This is a descriptive comparison of published history, not a forecast or recommendation.</p></header>
    <CompareExperience />
  </div></div>;
}
