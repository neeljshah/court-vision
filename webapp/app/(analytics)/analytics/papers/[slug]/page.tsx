import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PaperArticle } from "@/components/analytics/papers/PaperArticle";
import { loadPapers } from "@/lib/analytics/papers.server";
import { JsonLd } from "@/components/seo/JsonLd";
import { paperMeta } from "@/lib/seo/families";
import { paperJsonLd } from "@/lib/seo/jsonld";
import "../papers.css";

export const dynamicParams = false;

export function generateStaticParams() {
  return loadPapers().map(paper => ({ slug: paper.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const paper = loadPapers().find(entry => entry.slug === params.slug);
  if (!paper) return { title: "Research paper", description: "A CourtVision Analytics research paper." };
  return paperMeta({ slug: paper.slug, title: paper.title, abstract: paper.abstract, date: paper.date, sport: paper.sport });
}

export default function PaperPage({ params }: { params: { slug: string } }) {
  const paper = loadPapers().find(entry => entry.slug === params.slug);
  if (!paper) notFound();
  return (
    <div className="wrap paper-page">
      <Link href="/analytics/papers/" className="paper-back" prefetch={false}>&larr; Research papers</Link>
      <JsonLd data={paperJsonLd({ slug: paper.slug, title: paper.title, subtitle: paper.subtitle, abstract: paper.abstract, authors: paper.authors, date: paper.date, keywords: paper.keywords })} />
      <PaperArticle paper={paper} />
    </div>
  );
}
