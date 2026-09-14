import { describe, expect, it } from "vitest";
import { resolveQuestion } from "./askSearch";
import { loadScoutCorpus } from "./scoutCorpus";

const corpus = loadScoutCorpus();

describe("loadScoutCorpus", () => {
  it("keeps curated answers and expands all public entity and module records", () => {
    expect(corpus.length).toBe(2_088);
    expect(corpus.some((entry) => entry.q === "Does the model actually beat the betting market?")).toBe(true);
    expect(corpus.filter((entry) => entry.bucket === "public-entity-profile")).toHaveLength(1_549);
    expect(corpus.filter((entry) => entry.bucket === "public-analytics-module")).toHaveLength(74);
  });

  it("marks both curated full-season Brier answers as withdrawn corrections", () => {
    const answers = corpus.filter((entry) => /full-season.*backtest/i.test(entry.q));
    expect(answers).toHaveLength(2);
    for (const entry of answers) {
      expect(entry.a.answer).toContain("Correction published 2026-09-14");
      expect(entry.a.answer).toContain("withdrawn");
      expect(entry.a.as_of).toBe("2026-09-14");
      expect(entry.a.source_artifact).toBe("docs/JOB_EVIDENCE_PACKET.md");
    }
  });

  it("builds named entity profiles with metrics, source, and as-of scope", () => {
    const ohtani = corpus.find((entry) => entry.q === "What public metrics are available for Shohei Ohtani?");
    expect(ohtani).toMatchObject({
      a: {
        source_artifact: "webapp/public/data/showcase/atlas_mlb_batters_manifest.json",
        as_of: "2025-09-28",
      },
    });
    expect(ohtani?.a.answer).toContain("average exit velocity:");
    expect(ohtani?.a.answer).toContain("mph");
    expect(ohtani?.a.answer).toContain("not a current projection or live feed");
  });

  it("grounds player, unknown-person, and latest-data questions", () => {
    expect(resolveQuestion("How is Jokic's playmaking?", corpus)).toMatchObject({ kind: "direct", entry: { a: { status: "ok" } } });
    expect(resolveQuestion("What public profile is available for Wembanyama?", corpus)).toMatchObject({ kind: "direct", entry: { a: { status: "ok" } } });
    expect(resolveQuestion("Tell me about Ohtani", corpus)).toMatchObject({ kind: "direct", entry: { q: "What public metrics are available for Shohei Ohtani?" } });
    expect(resolveQuestion("What is Unknown Person's NBA profile?", corpus)?.kind).not.toBe("direct");
    expect(resolveQuestion("What are Ohtani's latest stats?", corpus)).toMatchObject({ kind: "direct", entry: { a: { status: "no_data" } } });
  });

  it("does not answer a named entity directly when the query adds conflicting scope", () => {
    const queries = [
      "Tell me about Ohtani basketball rebounds",
      "What public metrics are available for Jokic soccer",
      "How is Jokic baseball pitching?",
      "What public metrics are available for pitch type CH NBA",
      "What is Ohtani model calibration?",
    ];
    for (const query of queries) expect(resolveQuestion(query, corpus)?.kind).not.toBe("direct");
  });

  it("keeps follow-ups tied to entity-specific context", () => {
    const result = resolveQuestion("Tell me about Stephen Curry", corpus);
    expect(result?.followUps).not.toContain("What public metrics are available for AJ Lawson?");
  });

  it("does not treat the documented Live-Clock metric as a live-data request", () => {
    expect(resolveQuestion("What is Live-Clock Fraction?", corpus)).toMatchObject({
      kind: "direct",
      entry: { q: "What is the Live-Clock Fraction?", a: { status: "ok" } },
    });
    expect(resolveQuestion("What does the Novel Live Clock Fraction analytics module cover?", corpus)).toMatchObject({
      kind: "direct",
      entry: { q: "What does the Novel Live Clock Fraction analytics module cover?", a: { status: "ok" } },
    });
    expect(resolveQuestion("What is the latest Live-Clock Fraction?", corpus)).toMatchObject({
      kind: "direct",
      entry: { a: { status: "no_data" } },
    });
  });
});
