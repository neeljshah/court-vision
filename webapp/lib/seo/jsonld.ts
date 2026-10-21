// lib/seo/jsonld.ts -- minimal schema.org JSON-LD builders. Pure; rendered by
// components/seo/JsonLd.tsx. Nothing here says more than the page already prints:
// no ratings, no reviews, no claims. The Dataset builder refuses to run without a
// source URL and a license text taken from the artifact (a license is never invented).
import { CONTACT_EMAIL, GITHUB, PORTFOLIO } from "@/components/shell/nav";
import { SITE_DESCRIPTION, SITE_NAME, canonicalUrl, clampDescription } from "./meta";

export type JsonLd = Record<string, unknown>;
const CONTEXT = "https://schema.org";

/** The site's author, as the home byline prints: name, GitHub and portfolio. */
export function personJsonLd(): JsonLd {
  return { "@context": CONTEXT, "@type": "Person", "@id": `${canonicalUrl("/")}#author`, name: "Neel Shah", url: PORTFOLIO, email: `mailto:${CONTACT_EMAIL}`, sameAs: [GITHUB, PORTFOLIO] };
}

/** The site itself (root page only). */
export function websiteJsonLd(): JsonLd {
  return { "@context": CONTEXT, "@type": "WebSite", name: SITE_NAME, url: canonicalUrl("/"), description: SITE_DESCRIPTION, author: { "@id": `${canonicalUrl("/")}#author` } };
}

export type PaperLd = { slug: string; title: string; subtitle?: string; abstract: string; authors: string[]; date: string; keywords?: string[] };
/** A research paper as a ScholarlyArticle; datePublished is the paper's own date. */
export function paperJsonLd(p: PaperLd): JsonLd {
  return {
    "@context": CONTEXT,
    "@type": "ScholarlyArticle",
    headline: p.title,
    ...(p.subtitle ? { alternativeHeadline: p.subtitle } : {}),
    description: clampDescription(p.abstract, 300),
    author: p.authors.map((name) => ({ "@type": "Person", name })),
    datePublished: p.date,
    ...(p.keywords?.length ? { keywords: p.keywords.join(", ") } : {}),
    url: canonicalUrl(`/analytics/papers/${p.slug}/`),
    isAccessibleForFree: true,
    inLanguage: "en",
  };
}

export type DatasetLd = { slug: string; name: string; description: string; sourceUrl?: string | null; license?: string | null; dateModified?: string | null };
/** A finding's artifact as a Dataset, only when the page shows a source URL and a license text. */
export function datasetJsonLd(d: DatasetLd): JsonLd | null {
  const license = typeof d.license === "string" ? d.license.trim() : "";
  const source = typeof d.sourceUrl === "string" && /^https?:\/\//.test(d.sourceUrl) ? d.sourceUrl : "";
  if (!license || !source) return null;
  return {
    "@context": CONTEXT,
    "@type": "Dataset",
    name: d.name,
    description: clampDescription(d.description, 300),
    url: canonicalUrl(`/analytics/findings/${d.slug}/`),
    distribution: { "@type": "DataDownload", contentUrl: source, encodingFormat: "application/json" },
    license,
    ...(d.dateModified ? { dateModified: d.dateModified } : {}),
  };
}

/** Serialise for a <script type="application/ld+json">; "<" is escaped so no tag can close the script. */
export function serializeJsonLd(data: JsonLd | JsonLd[]): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
