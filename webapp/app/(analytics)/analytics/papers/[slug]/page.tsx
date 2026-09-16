import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PaperArticle } from "@/components/analytics/papers/PaperArticle";
import { loadPapers } from "@/lib/analytics/papers.server";
import { excerpt } from "@/lib/analytics/papers";
import "../papers.css";

export const dynamicParams = false;

export function generateStaticParams() {
  return loadPapers().map(paper => ({ slug: paper.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const paper = loadPapers().find(entry => entry.slug === params.slug);
  return {
    title: paper ? paper.title : "Research paper",
    description: paper ? excerpt(paper.abstract, 180) : "A CourtVision Analytics research paper.",
  };
}

export default function PaperPage({ params }: { params: { slug: string } }) {
  const paper = loadPapers().find(entry => entry.slug === params.slug);
  if (!paper) notFound();
  return (
    <div className="wrap paper-page">
      <Link href="/analytics/papers/" className="paper-back" prefetch={false}>&larr; Research papers</Link>
      <PaperArticle paper={paper} />
    </div>
  );
}
