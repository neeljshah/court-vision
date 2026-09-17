import { describe, expect, it } from "vitest";
import { loadPapers } from "./papers.server";
import { bestPaperForInspector, paperBacklinks, readingEntries } from "./related.server";

describe("server reading entries", () => {
  const entries = readingEntries();
  const papers = loadPapers();

  it("adds every validated paper with its public route and source modules", () => {
    const paperEntries = entries.filter((entry) => entry.kind === "paper");
    expect(paperEntries).toHaveLength(papers.length);
    paperEntries.forEach((entry) => {
      expect(entry.href).toBe(`/analytics/papers/${entry.id}/`);
      expect(entry.sources?.length).toBeGreaterThan(0);
    });
  });

  it("returns reciprocal inspector backlinks for every declared inspector", () => {
    papers.forEach((paper) => paper.related.filter((target) => target.kind === "inspector").forEach((target) => {
      expect(paperBacklinks("inspector", target.id, entries).map((link) => link.id)).toContain(paper.slug);
    }));
  });

  it("returns a backlink for every sport-compatible evidence module", () => {
    papers.forEach((paper) => paper.evidence.forEach((evidence) => {
      const source = entries.find((entry) => entry.kind === "module" && entry.id === evidence.module);
      if (source && (paper.sport === "all" || source.sport === "all" || source.sport === paper.sport)) {
        expect(paperBacklinks("module", evidence.module!, entries).map((link) => link.id)).toContain(paper.slug);
      }
    }));
  });

  it("does not attach an NBA paper to a tennis module", () => {
    const nbaPaper = entries.find((entry) => entry.kind === "paper" && entry.sport === "nba");
    const tennisModule = entries.find((entry) => entry.kind === "module" && entry.sport === "tennis");
    if (nbaPaper && tennisModule) expect(paperBacklinks("module", tennisModule.id, entries).map((link) => link.id)).not.toContain(nbaPaper.id);
  });

  it("marks affected module backlinks as regenerated sources", () => {
    const links = paperBacklinks("module", "state_conditioned_calibration", entries);
    expect(links.length).toBeGreaterThan(0);
    expect(links.every((link) => link.title.endsWith("(sources regenerated)"))).toBe(true);
  });

  it("chooses one inspector analysis by source overlap before its title", () => {
    const best = bestPaperForInspector("state-reliability", entries);
    expect(best?.id).toBe("how-to-read-a-courtvision-paper");
  });
});
