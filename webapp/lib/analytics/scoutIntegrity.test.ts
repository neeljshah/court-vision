import { describe, expect, it } from "vitest";
import curatedJson from "../../public/data/ask/corpus.json";
import { analysisDestinations } from "./analysisDestinations";
import type { AskEntry } from "./askSearch";
import { buildReadingRoomAnswers } from "./scoutInspectorAnswers";
import { scoutIntegrity, sourceModuleIds } from "./scoutIntegrity";

const curated = (curatedJson as unknown as { entries: AskEntry[] }).entries;

describe("Scout integrity metadata", () => {
  it("warns on the published calibration answer while preserving its cited status", () => {
    const entry = curated.find(item => item.q === "Are the predictions actually well calibrated?");
    expect(entry?.a.status).toBe("ok");
    expect(scoutIntegrity(entry!.a)).toMatchObject({
      moduleIds: ["calibration_stability"],
      notices: [
        { status: "withdrawn-pending-regeneration" },
        { status: "under-review" },
      ],
    });
  });

  it("extracts only exact JSON artifact ids without guessing from prose", () => {
    expect(sourceModuleIds([
      "webapp/public/data/showcase/calibration_stability.json -> sports.mlb",
      "webapp\\public\\data\\showcase\\calibration_stability.json",
      "calibration_stability appears in prose",
      "docs/evidence/calibration-decomposition.md",
    ])).toEqual(["calibration_stability"]);
    expect(scoutIntegrity({ status: "ok", answer: "murphy_decomposition is discussed", source_artifact: "safe.json" }).notices).toEqual([]);
  });

  it("carries every inspector's complete registered source list", () => {
    const artifacts = Array.from(new Set(analysisDestinations.flatMap(destination => destination.sourceModuleIds))).map(id => ({
      id,
      artifact: `webapp/public/data/showcase/${id}.json`,
      asOf: null,
      data: {},
    }));
    const answers = buildReadingRoomAnswers(artifacts, [], []);
    for (const destination of analysisDestinations) {
      const answer = answers.find(entry => entry.a.explore_path === destination.route);
      expect(answer?.a.source_module_ids, destination.id).toEqual(destination.sourceModuleIds);
    }
    const calibration = answers.find(entry => entry.a.explore_path === "/analytics/calibration");
    expect(scoutIntegrity(calibration!.a).notices).toHaveLength(2);
  });

  it("uses exact explainer and paper citations and leaves safe records clear", () => {
    const answers = buildReadingRoomAnswers([], [{
      slug: "reliability",
      title: "Reliability",
      cited: ["webapp/public/data/showcase/calibration_stability.json -> sports.mlb", "docs/reliability.md"],
    }, {
      slug: "safe",
      title: "Safe",
      cited: ["webapp/public/data/showcase/site_manifest.json"],
    }], [{
      slug: "decomposition",
      title: "Decomposition",
      date: "2026-09-16",
      abstract: "Published decomposition.",
      evidence: [{ artifact: "murphy_decomposition.json" }, { artifact: "why_attribution.json" }],
    }]);
    const reliability = answers.find(entry => entry.a.explore_path === "/analytics/explainers/reliability/")!;
    const paper = answers.find(entry => entry.a.explore_path === "/analytics/papers/decomposition/")!;
    const safe = answers.find(entry => entry.a.explore_path === "/analytics/explainers/safe/")!;

    expect(reliability.a.source_module_ids).toEqual(["calibration_stability"]);
    expect(scoutIntegrity(reliability.a).notices).toHaveLength(2);
    expect(paper.a.source_module_ids).toEqual(["murphy_decomposition", "why_attribution"]);
    expect(scoutIntegrity(paper.a).notices).toHaveLength(2);
    expect(scoutIntegrity(safe.a).notices).toEqual([]);
  });
});
