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
});
