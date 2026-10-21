import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { datasetJsonLd, paperJsonLd, personJsonLd, serializeJsonLd, websiteJsonLd } from "@/lib/seo/jsonld";
import { GITHUB, PORTFOLIO } from "@/components/shell/nav";

beforeEach(() => vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision"));
afterEach(() => vi.unstubAllEnvs());

describe("JSON-LD builders", () => {
  it("WebSite + Person on the root carry the byline's GitHub and portfolio and nothing more", () => {
    const site = websiteJsonLd();
    const person = personJsonLd();
    expect(site).toMatchObject({ "@type": "WebSite", name: "CourtVision", url: "https://neeljshah.github.io/court-vision/" });
    expect(person).toMatchObject({ "@type": "Person", name: "Neel Shah", sameAs: [GITHUB, PORTFOLIO] });
    for (const o of [site, person]) for (const k of ["aggregateRating", "review", "jobTitle"]) expect(o).not.toHaveProperty(k);
  });
  it("ScholarlyArticle takes datePublished from the paper's own date", () => {
    const a = paperJsonLd({ slug: "s", title: "T", subtitle: "S", abstract: "A.", authors: ["Neel Shah"], date: "2026-09-10", keywords: ["k"] });
    expect(a).toMatchObject({ "@type": "ScholarlyArticle", headline: "T", datePublished: "2026-09-10", url: "https://neeljshah.github.io/court-vision/analytics/papers/s/", author: [{ "@type": "Person", name: "Neel Shah" }] });
  });
  it("Dataset is emitted only with a source URL and a license text, never invented", () => {
    const base = { slug: "f", name: "F", description: "d" };
    expect(datasetJsonLd({ ...base })).toBeNull();
    expect(datasetJsonLd({ ...base, sourceUrl: "https://example.org/a.json" })).toBeNull();
    expect(datasetJsonLd({ ...base, license: "CC0-1.0" })).toBeNull();
    expect(datasetJsonLd({ ...base, license: " ", sourceUrl: "https://example.org/a.json" })).toBeNull();
    expect(datasetJsonLd({ ...base, license: "CC0-1.0", sourceUrl: "scripts/a.json" })).toBeNull();
    expect(datasetJsonLd({ ...base, license: "CC0-1.0", sourceUrl: "https://example.org/a.json" })).toMatchObject({ "@type": "Dataset", license: "CC0-1.0", distribution: { contentUrl: "https://example.org/a.json" } });
  });
  it("serialises with < escaped so a value can never close the script tag", () => {
    expect(serializeJsonLd({ a: "</script><b>" })).toBe('{"a":"\\u003c/script>\\u003cb>"}');
  });
});
