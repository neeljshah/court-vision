import type { Metadata } from "next";
import PapersIndex from "@/components/analytics/papers/PapersIndex";
import { loadPapers } from "@/lib/analytics/papers.server";
import "./papers.css";

export const metadata: Metadata = {
  title: "Research papers",
  description: "Method notes on calibration and description, each one naming the committed artifact and field path behind every number it prints.",
};

export default function PapersIndexPage() {
  return <PapersIndex papers={loadPapers()} />;
}
