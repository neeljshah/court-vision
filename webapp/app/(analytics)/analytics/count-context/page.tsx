import type { Metadata } from "next";
import Link from "next/link";
import { CountContext } from "@/components/analytics/count-context/CountContext";
import { ExactCountExplorer } from "@/components/analytics/count-context/ExactCountExplorer";
import { InspectorReadingTrail } from "@/components/analytics/InspectorReadingTrail";
import { loadCountContext, loadExactCountContext } from "@/lib/analytics/countContext.server";
import "./count-context.css";

export const metadata: Metadata = {
  title: "Count context",
  description: "Compare MLB pitch profiles by exact ball-strike count, then inspect count-class pitch mixes and outcome proxies.",
};

export default function CountContextPage() {
  const data = loadCountContext();
  const exact = loadExactCountContext();
  return <div className="cc-page">
    <p className="cc-kicker">MLB / Descriptive count context</p>
    <h1>Pitch profiles for every count.</h1>
    <p className="cc-intro">Explore pitch selection and recorded outcomes by the balls and strikes before a pitch. Compare individual counts, then inspect broader count classes in the published local 2025 Statcast snapshot.</p>
    <nav className="cc-section-links" aria-label="Count-context sections"><Link href="/analytics/count-context/#exact-count">Explore exact counts</Link><Link href="/analytics/count-context/#count-classes">Compare count classes</Link></nav>
    <div id="exact-count" className="cc-anchor"><ExactCountExplorer data={exact} /></div>
    <section id="count-classes" className="cc-class-section" aria-labelledby="cc-classes-heading"><h2 id="cc-classes-heading">The broader count classes</h2><p className="cc-intro">These grouped views publish separate rate denominators. Their overlapping samples cannot be added to the partition.</p><CountContext data={data} /></section>
    <InspectorReadingTrail id="count-context" />
  </div>;
}
