import type { Metadata } from "next";
import PapersIndex from "@/components/analytics/papers/PapersIndex";
import { loadPapers } from "@/lib/analytics/papers.server";
import { toPaperCard } from "@/lib/analytics/papers";
import { WorkingPapers } from "@/components/analytics/papers/WorkingPapers";
import { loadWorkingPapers } from "@/lib/analytics/workingPapers.server";
import "./papers.css";
import { pageMeta } from "@/lib/seo/meta";

export const metadata: Metadata = pageMeta("/analytics/papers/", {
  title: "Research papers",
  description: "Method notes on calibration and description, each one naming the committed artifact and field path behind every number it prints.",
});

export default function PapersIndexPage() {
  // Cards, not full papers: PapersIndex is a client component, so its props are
  // serialised into the exported HTML twice; the full bodies were 676 KB of it.
  return <>
    <PapersIndex papers={loadPapers().map(toPaperCard)} />
    <WorkingPapers papers={loadWorkingPapers()} />
  </>;
}
