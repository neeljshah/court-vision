import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadPapers, publishedArtifacts, resolveRelated } from "./papers.server";
import {
  excerpt, filterPapers, paperKeywords, paperSports, paperWordCount, readingMinutes,
  relatedHref, sortPapers, validatePaper, type Paper,
} from "./papers";

const SAMPLE = "how-to-read-a-courtvision-paper";

function sample(): Record<string, unknown> {
  const path = join(process.cwd(), "public", "data", "papers", `${SAMPLE}.json`);
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

describe("validatePaper", () => {
  const artifacts = publishedArtifacts();

  it("accepts the committed sample paper", () => {
    expect(validatePaper(sample(), artifacts)).toBeNull();
  });

  it("rejects a paper that uses prohibited vocabulary", () => {
    const paper = sample();
    const sections = paper.sections as Array<{ blocks: unknown[] }>;
    sections[0].blocks = [{ type: "p", text: "This paragraph claims an edge over the close." }];
    expect(validatePaper(paper, artifacts)).toMatch(/prohibited vocabulary/);
  });
  it("forbids bookmaker as prose but lets a paper cite the bookmaker_accuracy module id", () => {
    const prose = sample();
    (prose.sections as Array<{ blocks: unknown[] }>)[0].blocks = [{ type: "p", text: "The bookmaker moved first." }];
    expect(validatePaper(prose, artifacts)).toMatch(/prohibited vocabulary/);
    const cited = sample();
    (cited.sections as Array<{ blocks: unknown[] }>)[0].blocks = [{ type: "p", text: "Source rows come from bookmaker_accuracy.json and its sports.tennis.books[] entries." }];
    expect(validatePaper(cited, artifacts)).toBeNull();
  });

  it("rejects an unknown block type", () => {
    const paper = sample();
    const sections = paper.sections as Array<{ blocks: unknown[] }>;
    sections[0].blocks = [{ type: "video", src: "clip.mp4" }];
    expect(validatePaper(paper, artifacts)).toMatch(/unknown block type video/);
  });

  it("rejects an evidence artifact that is not published", () => {
    const paper = sample();
    const evidence = paper.evidence as Array<{ artifact: string }>;
    evidence[0].artifact = "not_a_published_artifact.json";
    expect(validatePaper(paper, artifacts)).toMatch(/not_a_published_artifact\.json.+not a published artifact/);
  });

  it("rejects non-ASCII text and a malformed slug", () => {
    const withUnicode = { ...sample(), subtitle: "A subtitle with a dash — here" };
    expect(validatePaper(withUnicode, artifacts)).toMatch(/non-ASCII/);
    expect(validatePaper({ ...sample(), slug: "Not A Slug" }, artifacts)).toMatch(/kebab-case/);
  });
});

describe("loadPapers", () => {
  it("returns only valid papers, sorted by date then title", () => {
    const papers = loadPapers();
    const artifacts = publishedArtifacts();
    expect(papers.length).toBeGreaterThan(0);
    expect(papers.map(paper => paper.slug)).toContain(SAMPLE);
    papers.forEach(paper => expect(validatePaper(paper, artifacts)).toBeNull());
    expect(papers).toEqual(sortPapers(papers));
  });

  it("titles related links through the published registries", () => {
    const paper = loadPapers().find(entry => entry.slug === SAMPLE) as Paper;
    const resolved = resolveRelated(paper.related, [paper]);
    expect(resolved).toHaveLength(paper.related.length);
    expect(resolved.map(link => link.href)).toEqual(paper.related.map(relatedHref));
    expect(resolved.every(link => link.title.length > 0)).toBe(true);
    expect(resolved.find(link => link.kind === "inspector")?.href).toBe("/analytics/calibration/");
  });
});

describe("reading helpers", () => {
  const paper = loadPapers().find(entry => entry.slug === SAMPLE) as Paper;

  it("counts the words of the sample inside the contract range", () => {
    const words = paperWordCount(paper);
    expect(words).toBeGreaterThanOrEqual(1500);
    expect(words).toBeLessThanOrEqual(2500);
    expect(readingMinutes(paper)).toBe(Math.max(1, Math.round(words / 220)));
  });

  it("filters by sport and keyword and lists the chips from the data", () => {
    expect(filterPapers([paper], "any", "any")).toHaveLength(1);
    expect(filterPapers([paper], paper.sport, paper.keywords[0])).toHaveLength(1);
    expect(filterPapers([paper], "tennis", "any")).toHaveLength(0);
    expect(paperSports([paper])).toEqual([paper.sport]);
    expect(paperKeywords([paper])).toEqual([...paper.keywords].sort((a, b) => a.localeCompare(b)));
  });

  it("truncates an excerpt on a word boundary", () => {
    expect(excerpt("one two three", 40)).toBe("one two three");
    expect(excerpt(paper.abstract, 80).endsWith("...")).toBe(true);
    expect(excerpt(paper.abstract, 80).length).toBeLessThanOrEqual(83);
  });
  it("rejects a related module without a module page and accepts evidence without a module id", () => {
    const paper = sample();
    (paper.related as Array<{ kind: string; id: string }>).push({ kind: "module", id: "atlas_only" });
    const base = sample();
    const routable = new Set([...(base.evidence as Array<{ module: string }>).map((entry) => entry.module), ...(base.related as Array<{ kind: string; id: string }>).filter((link) => link.kind === "module").map((link) => link.id)]);
    expect(validatePaper(paper, new Set([...publishedArtifacts(), "atlas_only.json"]), { moduleIds: routable })).toMatch(/has no published module page/);
    const cited = sample();
    const entry = (cited.evidence as Array<Record<string, unknown>>)[0];
    delete entry.module;
    expect(validatePaper(cited, publishedArtifacts(), { moduleIds: routable })).toBeNull();
  });
});
