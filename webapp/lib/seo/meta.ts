// lib/seo/meta.ts -- the ONE place a page's canonical URL, description length and social
// tags come from. Pure (no node:fs) so the family generators and their tests can import it.
//
//   export const metadata = pageMeta("/about/", { title: "About", description: "..." });
//
// pageMeta returns a Next Metadata object: the title (the root layout appends " | CourtVision"),
// a description clamped under 160 characters, <link rel="canonical"> as the absolute
// trailing-slash URL, og:url / og:type / og:site_name / og:image (title and description fill
// from the page's own), twitter:card summary_large_image, and robots noindex when asked.
// Calibration language only: a description never claims an edge, ROI or profit.
import type { Metadata } from "next";
import { VERDICT_QUALIFIER, isPacketVerdict } from "@/lib/packetVerdicts";

export const SITE_NAME = "CourtVision";
export const DESCRIPTION_MAX = 160;
export const SITE_DESCRIPTION =
  "Calibrated NBA, MLB, soccer and tennis forecasts scored against devigged closing markets, losses and retractions included. Paper units only.";

export const siteOrigin = (): string => process.env.NEXT_PUBLIC_SITE_URL || "https://neeljshah.github.io";
export const basePath = (): string => process.env.NEXT_PUBLIC_BASE_PATH || "";

/** The absolute URL of a basePath-free route, always with a trailing slash (next.config trailingSlash). */
export function canonicalUrl(route: string): string {
  const path = route.startsWith("/") ? route : `/${route}`;
  return `${siteOrigin()}${basePath()}${path.endsWith("/") ? path : `${path}/`}`;
}

/** Whitespace-normalised text cut under `max` characters at a word boundary, "..." when cut. */
export function clampDescription(text: string, max = DESCRIPTION_MAX - 1): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, Math.max(0, max - 3));
  const atWord = cut.lastIndexOf(" ");
  const kept = atWord > max / 2 ? cut.slice(0, atWord) : cut;
  return `${kept.replace(/[\s,;:.-]+$/, "")}...`;
}

/** `body` clamped so that `suffix` (a verdict or as-of sentence) always survives under the limit. */
export function fitDescription(body: string, suffix = ""): string {
  const tail = suffix.replace(/\s+/g, " ");
  return `${clampDescription(body, DESCRIPTION_MAX - 1 - tail.length)}${tail}`;
}

/** A packet verdict with the qualifier the packet attaches; any other token reads as plain words. */
export function verdictLabel(verdict: unknown): string {
  if (isPacketVerdict(verdict)) {
    const q = VERDICT_QUALIFIER[verdict];
    return q ? `${verdict} (${q})` : verdict;
  }
  return typeof verdict === "string" && verdict.trim() ? verdict.trim().replace(/_/g, " ").toLowerCase() : "no packet verdict";
}

export function defaultOgImage() {
  return { url: `${basePath()}/brand/og-analytics.png`, width: 1200, height: 630, alt: "CourtVision: a calibrated forecaster and its public scorecard." };
}

export type PageMeta = {
  title: string;
  description: string;
  /** Redirect stubs: noindex, follow. */
  noindex?: boolean;
  /** Override the canonical (a redirect stub points at its destination). */
  canonical?: string;
  type?: "website" | "article";
};

type OgImages = NonNullable<Extract<Metadata["openGraph"], { images?: unknown }>["images"]>;
type TwImages = NonNullable<Extract<Metadata["twitter"], { images?: unknown }>["images"]>;
/** Per-page overrides, e.g. a finding's own social card: { openGraph: { images }, twitter: { images } }. */
export type MetaExtra = { openGraph?: { images?: OgImages }; twitter?: { images?: TwImages } };

export function pageMeta(route: string, page: PageMeta, extra: MetaExtra = {}): Metadata {
  const url = page.canonical ?? canonicalUrl(route);
  const description = clampDescription(page.description);
  const ogImages = extra.openGraph?.images ?? [defaultOgImage()];
  const twImages = extra.twitter?.images ?? [defaultOgImage().url];
  return {
    title: page.title,
    description,
    ...(page.noindex ? { robots: { index: false, follow: true } } : {}),
    alternates: { canonical: url },
    // og:title / og:description are left unset on purpose: Next fills them from the page's
    // own (templated) title and description, so they can never drift from the <title>.
    openGraph: { type: page.type ?? "website", siteName: SITE_NAME, url, images: ogImages },
    twitter: { card: "summary_large_image", images: twImages },
  };
}
