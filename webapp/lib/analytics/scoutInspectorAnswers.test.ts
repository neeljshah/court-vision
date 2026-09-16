import { describe, expect, it } from "vitest";
import { analysisDestinations } from "./analysisDestinations";
import { resolveQuestion } from "./askSearch";
import { loadScoutCorpus } from "./scoutCorpus.server";

const corpus = loadScoutCorpus();

describe("Scout reading-room answers", () => {
  it("gives every inspector its exact answer and registered destination", () => {
    for (const destination of analysisDestinations) {
      const result = resolveQuestion(destination.title, corpus);
      expect(result, destination.title).toMatchObject({ kind: "direct", entry: { bucket: "public-inspector", a: { explore_path: destination.route } } });
    }
  });

  it("gives every published explainer a cited answer and destination", () => {
    const explainers = corpus.filter(entry => entry.bucket === "public-explainer");
    expect(explainers.length).toBeGreaterThan(0);
    expect(explainers.every(entry => /^\/analytics\/explainers\/[a-z0-9-]+\/$/.test(entry.a.explore_path || ""))).toBe(true);
  });

  it("lists authored support by sport without collapsing State contrasts to one bucket", () => {
    const answerFor = (id: string) => corpus.find(entry => entry.bucket === "public-inspector" && entry.a.explore_path === `/analytics/${id}`)?.a.answer || "";
    expect(answerFor("residual-anatomy")).toContain("MLB: 78,986 forecast observations; International soccer: 9,003 forecast observations");
    const contrasts = answerFor("state-contrasts");
    expect(contrasts).toContain("MLB from state: 2,458 cells; MLB to state: 2,079 cells");
    expect(contrasts).toContain("International soccer from state: 109 cells; International soccer to state: 176 cells");
    expect(contrasts).not.toContain("Published support: n=2,458");
  });

  it("uses each paper abstract's first sentence without a mechanical prefix", () => {
    const papers = corpus.filter(entry => entry.bucket === "public-paper");
    expect(papers.length).toBeGreaterThan(0);
    expect(papers.every(entry => !entry.a.answer.includes("It measures"))).toBe(true);
  });
});
