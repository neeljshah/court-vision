import { describe, it, expect } from "vitest";
import { resolveEvidenceHref, rewriteEvidenceLinks } from "../evidenceLinks";

const GH = "https://github.com/neeljshah/court-vision";
const slugs = new Set(["retraction-story", "leak-instruments"]);

describe("resolveEvidenceHref", () => {
  it("maps parent-relative docs to their GitHub blob URL", () => {
    expect(resolveEvidenceHref("../JOB_EVIDENCE_PACKET.md", slugs)).toBe(`${GH}/blob/master/docs/JOB_EVIDENCE_PACKET.md`);
    expect(resolveEvidenceHref("../../README.md", slugs)).toBe(`${GH}/blob/master/README.md`);
    expect(resolveEvidenceHref("../img/claims_corpus_meta.png", slugs)).toBe(`${GH}/blob/master/docs/img/claims_corpus_meta.png`);
  });

  it("maps a sibling claim file to its exported page under the base path", () => {
    expect(resolveEvidenceHref("retraction-story.md", slugs, "/court-vision")).toBe("/court-vision/evidence/retraction-story/");
    expect(resolveEvidenceHref("leak-instruments.md#receipts", slugs)).toBe("/evidence/leak-instruments/#receipts");
  });

  it("maps a sibling non-claim file and a directory to GitHub", () => {
    expect(resolveEvidenceHref("HARNESS_GAPS_2026-09-03.md", slugs)).toBe(`${GH}/blob/master/docs/evidence/HARNESS_GAPS_2026-09-03.md`);
    expect(resolveEvidenceHref("../../scripts/platformkit/analytics_showcase/out/", slugs)).toBe(`${GH}/tree/master/scripts/platformkit/analytics_showcase/out/`);
  });

  it("leaves absolute URLs, site-absolute paths, anchors and mailto alone", () => {
    for (const href of ["https://example.org/x", "/evidence/retraction-story", "#receipts", "mailto:neeljshah22@gmail.com"]) {
      expect(resolveEvidenceHref(href, slugs)).toBe(href);
    }
  });
});

describe("rewriteEvidenceLinks", () => {
  it("rewrites link targets but never image sources", () => {
    const md = "See [the packet](../JOB_EVIDENCE_PACKET.md) and ![fig](../img/x.png).\n[Story](retraction-story.md)";
    expect(rewriteEvidenceLinks(md, slugs, "/court-vision")).toBe(
      `See [the packet](${GH}/blob/master/docs/JOB_EVIDENCE_PACKET.md) and ![fig](../img/x.png).\n[Story](/court-vision/evidence/retraction-story/)`,
    );
  });
});
