import { describe, expect, it } from "vitest";
import { loadPitchSequencing } from "./pitchSequencing.server";
import { buildPitchSequencing, pitchCell } from "./pitchSequencing";

const fixture = {
  as_of: "2026-07-25", floors: { row_min_n: 200 }, pitch_types: ["FF", "SL"],
  by_class: [{ class: "behind", definition: "published definition", overlapping: false, coverage: 0.9, row_n_from: [10, 4], row_below_floor: [false, true], count_matrix: [[2, 3], [1, 1]], prob_matrix: [[0.2, 0.3], [0.25, 0.25]] }],
};

describe("pitch sequencing data", () => {
  it("keeps row and column axes aligned to their published pitch types", () => {
    const data = buildPitchSequencing(fixture);
    expect(pitchCell(data, data.classes[0], 0, 1)).toMatchObject({ from: "FF", to: "SL", count: 3, denominator: 10, probability: 0.3 });
  });

  it("marks a masked source row without hiding its published denominator", () => {
    const data = buildPitchSequencing(fixture);
    expect(pitchCell(data, data.classes[0], 1, 0)).toMatchObject({ masked: true, denominator: 4, count: 1 });
  });

  it("retains the published overlap state and does not renormalize a row", () => {
    const data = buildPitchSequencing({ ...fixture, by_class: [{ ...fixture.by_class[0], class: "two_strike", overlapping: true }] });
    expect(data.classes[0].overlapping).toBe(true);
    expect(data.classes[0].probabilityMatrix[0]).toEqual([0.2, 0.3]);
  });

  it("loads the committed browser-safe snapshot without changing its published axes", () => {
    const data = loadPitchSequencing();
    expect(data).toMatchObject({
      pitchTypes: ["FF", "SI", "SL", "CH", "ST", "FC", "CU", "FS"],
      rowMinN: 200,
      asOf: "2026-07-25T11:13:31.944905+00:00",
    });
    expect(data.classes.map(item => item.id)).toEqual(["all", "behind", "even", "ahead", "two_strike", "three_ball"]);
  });
});
