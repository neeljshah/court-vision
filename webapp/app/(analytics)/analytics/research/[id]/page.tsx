import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getResearchAnalyses } from "@/lib/analytics/researchData";
import ResearchDetail from "@/components/analytics/library/ResearchDetail";
import { RelatedReading } from "@/components/analytics/RelatedReading";
import "../../workspace.css";
import "../../lab/lab.css";
import "../research.css";
import "../measurement-coverage.css";
import "../brier-phase-coverage.css";
export function generateStaticParams() { return getResearchAnalyses().map(a => ({ id: a.id })); }
export function generateMetadata({ params }: { params: { id: string } }): Metadata {
  const a = getResearchAnalyses().find(a => a.id === params.id);
  return { title: a?.title || "Analysis unavailable", description: a?.description };
}
export default function ResearchPage({ params }: { params: { id: string } }) {
  const analyses = getResearchAnalyses(), analysis = analyses.find(a => a.id === params.id);
  if (!analysis) notFound();
  return <><ResearchDetail analysis={analysis} related={[]} /><div className="cv-workspace"><div className="cv-workspace-inner"><RelatedReading kind="analysis" id={analysis.id} /></div></div></>;
}
