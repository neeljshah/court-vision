import { describe, expect, it } from "vitest";
import { GET } from "./route";
import { loadPapers } from "@/lib/analytics/papers.server";
import { resolveRedirect } from "@/lib/redirects";
import { REQUIRED_PAGES } from "@/scripts/check-search-index.mjs";

type Rec = { id: string; title: string; href: string; type: string };

describe("search-index.json", () => {
  it("lists the site pages, papers, findings and inspector pages, and no redirect stub", async () => {
    const { records } = (await GET().json()) as { records: Rec[] };
    const hrefs = new Set(records.map((record) => record.href.replace(/\/+$/, "") || "/"));
    for (const page of REQUIRED_PAGES) expect(hrefs.has(page), page).toBe(true);
    expect(records.filter((record) => record.type === "page").map((record) => record.title)).toEqual(expect.arrayContaining(["Calibration reliability", "Retraction record", "Paper record"]));
    for (const paper of loadPapers()) expect(hrefs.has(`/analytics/papers/${paper.slug}`), paper.slug).toBe(true);
    expect(records.filter((record) => record.href.startsWith("/analytics/findings/")).length).toBeGreaterThanOrEqual(16);
    for (const record of records) expect(resolveRedirect(record.href), `${record.id} -> ${record.href}`).toBeNull();
    expect(hrefs.has("/analytics")).toBe(false);
    expect(hrefs.has("/analytics/findings/retraction")).toBe(false);
    expect(new Set(records.map((record) => record.id)).size).toBe(records.length);
  });
});
