import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getResearchAnalyses } from "@/lib/analytics/researchData";
import ResearchDetail from "@/components/analytics/library/ResearchDetail";
import "../../workspace.css";
import "../../lab/lab.css";
import "../research.css";
export function generateStaticParams() { return getResearchAnalyses().map(a => ({ id: a.id })); }
export function generateMetadata({ params }: { params: { id: string } }): Metadata {
  const a = getResearchAnalyses().find(a => a.id === params.id);
  return { title: a?.title || "Analysis unavailable", description: a?.description };
}
export default function ResearchPage({ params }: { params: { id: string } }) {
  const analyses = getResearchAnalyses(), analysis = analyses.find(a => a.id === params.id);
  if (!analysis) notFound();
  const related = analyses.filter(a => a.id !== analysis.id && a.sport === analysis.sport).slice(0, 3).map(a => ({ id: a.id, title: a.title }));
  return <ResearchDetail analysis={analysis} related={related} />;
}
