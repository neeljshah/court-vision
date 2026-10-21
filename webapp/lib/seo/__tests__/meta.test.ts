import { afterEach, describe, expect, it, vi } from "vitest";
import { DESCRIPTION_MAX, SITE_DESCRIPTION, canonicalUrl, clampDescription, fitDescription, pageMeta, verdictLabel } from "@/lib/seo/meta";
import { RETRACTED_TOKENS } from "@/lib/packetVerdicts";

afterEach(() => vi.unstubAllEnvs());

describe("canonicalUrl", () => {
  it("is absolute, under the basePath, with a trailing slash", () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision");
    expect(canonicalUrl("/about")).toBe("https://neeljshah.github.io/court-vision/about/");
    expect(canonicalUrl("/")).toBe("https://neeljshah.github.io/court-vision/");
    expect(canonicalUrl("analytics/m/x/")).toBe("https://neeljshah.github.io/court-vision/analytics/m/x/");
  });
});

describe("clampDescription", () => {
  it("keeps short text, cuts long text at a word boundary under the limit", () => {
    expect(clampDescription("  two   words ")).toBe("two words");
    const long = Array.from({ length: 60 }, (_, i) => `word${i}`).join(" ");
    const cut = clampDescription(long);
    expect(cut.length).toBeLessThan(DESCRIPTION_MAX);
    expect(cut.endsWith("...")).toBe(true);
    expect(cut).toMatch(/ word\d+\.\.\.$/); // a whole word, then the ellipsis
  });
  it("fitDescription always keeps the suffix", () => {
    const out = fitDescription("x".repeat(400), " As of 2026-10-01.");
    expect(out.length).toBeLessThan(DESCRIPTION_MAX);
    expect(out.endsWith("... As of 2026-10-01.")).toBe(true);
  });
  it("the site description itself is under the limit and free of retracted figures", () => {
    expect(SITE_DESCRIPTION.length).toBeLessThan(DESCRIPTION_MAX);
    for (const t of RETRACTED_TOKENS) expect(SITE_DESCRIPTION).not.toContain(t);
  });
});

describe("verdictLabel", () => {
  it("renders packet verdicts with the packet qualifier and other tokens as plain words", () => {
    expect(verdictLabel("MATCHES_CLOSE")).toBe("MATCHES_CLOSE (underpowered)");
    expect(verdictLabel("TRAILS_CLOSE")).toBe("TRAILS_CLOSE");
    expect(verdictLabel("NO_MARKET_COMPARISON_IN_ARTIFACT")).toBe("no market comparison in artifact");
    expect(verdictLabel(undefined)).toBe("no packet verdict");
  });
});

describe("pageMeta", () => {
  it("sets canonical, og:url, og:type, site name, default images and the twitter card", () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision");
    const m = pageMeta("/about/", { title: "About", description: "What it is." });
    const url = "https://neeljshah.github.io/court-vision/about/";
    expect(m.title).toBe("About");
    expect(m.description).toBe("What it is.");
    expect(m.alternates?.canonical).toBe(url);
    expect(m.openGraph).toMatchObject({ url, type: "website", siteName: "CourtVision" });
    expect(m.twitter).toMatchObject({ card: "summary_large_image" });
    expect(m.robots).toBeUndefined();
    // og:title / og:description are left to Next so they follow the page title and description.
    expect((m.openGraph as { title?: unknown }).title).toBeUndefined();
  });
  it("noindex + canonical override for a redirect stub; extra images win over the default card", () => {
    const m = pageMeta("/today/", { title: "Page moved", description: "d", noindex: true, canonical: "https://x/y/" },
      { openGraph: { images: [{ url: "/brand/a.png" }] }, twitter: { images: ["/brand/a.png"] } });
    expect(m.robots).toEqual({ index: false, follow: true });
    expect(m.alternates?.canonical).toBe("https://x/y/");
    expect(m.openGraph).toMatchObject({ url: "https://x/y/", images: [{ url: "/brand/a.png" }] });
    expect(m.twitter).toMatchObject({ images: ["/brand/a.png"] });
  });
});
